import { useEffect, useState } from "react";

import { ApiError, getResult, type GroupResult, type PipelineResults } from "./api/client";
import MetricTable from "./MetricTable";
import SummaryCards from "./SummaryCards";

type ResultState =
  | { status: "loading" }
  | { status: "ready"; result: PipelineResults }
  | { status: "error"; message: string };

function errorMessage(error: unknown) {
  return error instanceof ApiError ? error.message : "결과를 불러오지 못했습니다";
}

function GroupSummary({ group }: { group: GroupResult }) {
  return (
    <section className="result-group" role="tabpanel" id={`panel-${group.name}`} aria-labelledby={`tab-${group.name}`}>
      <div className="result-group__header">
        <div><span>선택한 그룹</span><h3>{group.name}</h3></div>
        <strong>{group.files.length}개 파일</strong>
      </div>
      <SummaryCards group={group} />
      <MetricTable group={group} />
      <p className="result-files">파일 · {group.files.join(", ")}</p>
    </section>
  );
}

function ReadyResults({ result }: { result: PipelineResults }) {
  const [selected, setSelected] = useState(result.groups[0]?.name ?? "");
  useEffect(() => setSelected(result.groups[0]?.name ?? ""), [result]);
  const group = result.groups.find((item) => item.name === selected) ?? result.groups[0];
  function selectTab(index: number) {
    const next = result.groups[(index + result.groups.length) % result.groups.length];
    if (!next) return;
    setSelected(next.name);
    window.requestAnimationFrame(() => document.getElementById(`tab-${next.name}`)?.focus());
  }
  if (!group) return <div className="empty-panel empty-panel--results">
    <span className="empty-panel__icon" aria-hidden="true">○</span>
    <strong>표시할 그룹 결과가 없습니다</strong>
    <span>처리하지 못한 그룹이 있다면 아래 안내를 확인하세요.</span>
  </div>;
  return <>
    <div className="result-tabs" role="tablist" aria-label="결과 그룹 선택">
      {result.groups.map((item, index) => <button
        type="button" role="tab" id={`tab-${item.name}`} aria-controls={`panel-${item.name}`}
        aria-selected={item.name === group.name} tabIndex={item.name === group.name ? 0 : -1}
        key={item.name} onClick={() => setSelected(item.name)} onKeyDown={(event) => {
          if (event.key === "ArrowRight") { event.preventDefault(); selectTab(index + 1); }
          if (event.key === "ArrowLeft") { event.preventDefault(); selectTab(index - 1); }
          if (event.key === "Home") { event.preventDefault(); selectTab(0); }
          if (event.key === "End") { event.preventDefault(); selectTab(result.groups.length - 1); }
        }}
      >{item.name}<span>{item.reduced_rows.toLocaleString()}행</span></button>)}
    </div>
    <GroupSummary key={group.name} group={group} />
    {!!result.skipped.length && <aside className="result-skipped">
      <strong>처리하지 못한 그룹 {result.skipped.length}개</strong>
      {result.skipped.map((item) => <span key={item.name}>{item.name} · {item.reason}</span>)}
    </aside>}
  </>;
}

export default function ResultsPage({ jobId }: { jobId: string | null }) {
  const [state, setState] = useState<ResultState>({ status: "loading" });
  const [reload, setReload] = useState(0);
  useEffect(() => {
    if (!jobId) return;
    const controller = new AbortController();
    setState({ status: "loading" });
    getResult(jobId, { signal: controller.signal })
      .then((result) => { if (!controller.signal.aborted) setState({ status: "ready", result }); })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setState({ status: "error", message: errorMessage(error) });
        }
      });
    return () => controller.abort();
  }, [jobId, reload]);
  if (!jobId) return <section className="page-card"><span className="eyebrow">분석 결과</span><h2>작업 번호가 필요합니다</h2><p className="lead">업로드 화면에서 분석을 완료한 뒤 이동하세요.</p></section>;
  return <section className="page-card" aria-labelledby="results-title">
    <span className="eyebrow">분석 결과</span><h2 id="results-title">그룹별 축소 결과</h2>
    <p className="lead">그룹 탭을 선택해 해당 결과를 확인하세요.</p>
    {state.status === "loading" && <div className="result-loading" role="status">결과를 불러오고 있습니다…</div>}
    {state.status === "error" && <div className="result-error" role="alert"><strong>결과를 불러오지 못했습니다</strong><span>{state.message}</span><button type="button" className="text-button" onClick={() => setReload((value) => value + 1)}>다시 불러오기</button></div>}
    {state.status === "ready" && <ReadyResults result={state.result} />}
  </section>;
}
