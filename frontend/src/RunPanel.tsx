import { useEffect, useRef, useState } from "react";

import { ApiError, getRunStatus, startRun, type RunStatus } from "./api/client";

type ViewState =
  | { status: "idle" }
  | { status: "starting" }
  | { status: "polling"; run: RunStatus }
  | { status: "error"; message: string };

function message(error: unknown) {
  return error instanceof ApiError ? error.message : "실행 상태를 확인하지 못했습니다";
}

function useRunProcess(jobId: string, onComplete: (jobId: string) => void) {
  const [view, setView] = useState<ViewState>({ status: "idle" });
  const controller = useRef<AbortController | null>(null);
  const timer = useRef<number | null>(null);
  const completed = useRef(false);

  function stopPolling() {
    controller.current?.abort();
    controller.current = null;
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = null;
  }

  useEffect(() => {
    completed.current = false;
    setView({ status: "idle" });
    return stopPolling;
  }, [jobId]);

  async function poll() {
    const request = new AbortController();
    controller.current = request;
    try {
      const run = await getRunStatus(jobId, { signal: request.signal });
      if (controller.current !== request) return;
      setView({ status: "polling", run });
      if (run.state === "done") {
        stopPolling();
        if (!completed.current) {
          completed.current = true;
          onComplete(jobId);
        }
      } else if (run.state === "failed") {
        stopPolling();
      } else if (run.state === "idle") {
        stopPolling();
        setView({ status: "error", message: "실행된 작업이 없습니다. 분석을 다시 시작하세요." });
      } else {
        timer.current = window.setTimeout(() => { void poll(); }, 800);
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      if (controller.current === request) {
        stopPolling();
        setView({ status: "error", message: message(error) });
      }
    }
  }

  async function start() {
    if (view.status === "starting") return;
    stopPolling();
    setView({ status: "starting" });
    try {
      await startRun(jobId);
      await poll();
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        await poll();
      } else if (!(error instanceof DOMException && error.name === "AbortError")) {
        setView({ status: "error", message: message(error) });
      }
    }
  }

  return { view, poll, start };
}

export default function RunPanel({
  jobId,
  ready,
  onComplete,
}: {
  jobId: string;
  ready: boolean;
  onComplete: (jobId: string) => void;
}) {
  const { view, poll, start } = useRunProcess(jobId, onComplete);

  const run = view.status === "polling" ? view.run : null;
  const active = view.status === "starting" || !!run && ["queued", "running"].includes(run.state);
  return (
    <section className="run-panel" aria-labelledby="run-panel-title">
      <div>
        <span className="eyebrow">4단계 · 축소 실행</span>
        <h3 id="run-panel-title">준비한 설정으로 분석을 시작하세요</h3>
        <p>실행 중에도 현재 단계와 진행률을 확인할 수 있습니다.</p>
      </div>
      <button type="button" className="run-button" disabled={!ready || active} onClick={() => { void start(); }}>
        {view.status === "starting" ? "실행 요청 중…" : active ? "분석 중…" : "축소 분석 시작"}
      </button>
      {!ready && <p className="run-panel__hint">그룹 결정과 모든 컬럼 선택을 먼저 저장하세요.</p>}
      {(view.status === "starting" || run) && (
        <div className="run-progress" role="status" aria-live="polite">
          <div><strong>{run?.stage ?? "실행 준비"}</strong><span>{run?.progress ?? 0}%</span></div>
          <progress max="100" value={run?.progress ?? 0} aria-label="축소 분석 진행률" />
          {run?.state === "failed" && <p className="run-progress__error">{run.error ?? "분석에 실패했습니다."}</p>}
        </div>
      )}
      {view.status === "error" && (
        <div className="run-error" role="alert">
          <strong>실행 상태를 확인하지 못했습니다</strong><span>{view.message}</span>
          <button type="button" className="text-button" onClick={() => { void poll(); }}>상태 다시 확인</button>
        </div>
      )}
    </section>
  );
}
