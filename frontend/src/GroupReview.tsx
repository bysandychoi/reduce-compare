import { useEffect, useMemo, useRef, useState } from "react";

import { ApiError, getGroups, updateGroups, type GroupView } from "./api/client";
import ColumnReview from "./ColumnReview";
import RunPanel from "./RunPanel";

type LoadState = "loading" | "ready" | "error";
type SaveState = "idle" | "saving" | "saved" | "error";

function errorMessage(error: unknown, fallback: string) {
  return error instanceof ApiError ? error.message : fallback;
}

function decisionKey(groups: GroupView[]) {
  return groups.map(({ group_id, merge }) => `${group_id}:${merge}`).join("|");
}

function GroupCard({
  group,
  disabled,
  onChange,
}: {
  group: GroupView;
  disabled: boolean;
  onChange: (merge: boolean) => void;
}) {
  const title = group.group_id.replace(/^group-/, "그룹 ");
  return (
    <article className="group-card">
      <div className="group-card__header">
        <div>
          <h4>{title}</h4>
          <span>{group.files.length}개 파일 · {group.columns.length}개 컬럼</span>
        </div>
        <fieldset className="group-decision" disabled={disabled}>
          <legend className="sr-only">{title} 처리 방식</legend>
          <label className={group.merge ? "group-decision__selected" : undefined} onClick={() => { if (!disabled) onChange(true); }}>
            <input
              type="radio"
              name={`decision-${group.group_id}`}
              checked={group.merge}
              onChange={() => onChange(true)}
            />
            병합
          </label>
          <label className={!group.merge ? "group-decision__selected" : undefined} onClick={() => { if (!disabled) onChange(false); }}>
            <input
              type="radio"
              name={`decision-${group.group_id}`}
              checked={!group.merge}
              onChange={() => onChange(false)}
            />
            개별 처리
          </label>
        </fieldset>
      </div>
      <ul className="group-files" aria-label={`${title} 파일`}>
        {group.files.map((file) => <li key={file}>{file}</li>)}
      </ul>
      <ul className="group-columns" aria-label={`${title} 컬럼`}>
        {group.columns.map((column) => (
          <li key={column.name}><strong>{column.name}</strong><span>{column.kind}</span></li>
        ))}
      </ul>
    </article>
  );
}

function useGroupReview(jobId: string) {
  const [groups, setGroups] = useState<GroupView[]>([]);
  const [baseline, setBaseline] = useState("");
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [message, setMessage] = useState("");
  const [reload, setReload] = useState(0);
  const saveRequest = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoadState("loading");
    setMessage("");
    getGroups(jobId, { signal: controller.signal }).then((view) => {
      if (controller.signal.aborted) return;
      setGroups(view.groups);
      setBaseline(decisionKey(view.groups));
      setLoadState("ready");
      setSaveState("idle");
    }).catch((error: unknown) => {
      if (controller.signal.aborted) return;
      setMessage(errorMessage(error, "그룹 정보를 불러오지 못했습니다"));
      setLoadState("error");
    });
    return () => controller.abort();
  }, [jobId, reload]);

  useEffect(() => () => saveRequest.current?.abort(), []);

  const dirty = useMemo(() => decisionKey(groups) !== baseline, [groups, baseline]);

  function changeDecision(groupId: string, merge: boolean) {
    setGroups((current) => current.map((group) => (
      group.group_id === groupId ? { ...group, merge } : group
    )));
    setSaveState("idle");
    setMessage("");
  }

  async function saveDecisions() {
    if (!dirty || saveRequest.current) return;
    const controller = new AbortController();
    saveRequest.current = controller;
    setSaveState("saving");
    setMessage("");
    try {
      const update = { groups: groups.map(({ group_id, merge }) => ({ group_id, merge })) };
      const view = await updateGroups(jobId, update, { signal: controller.signal });
      if (saveRequest.current !== controller) return;
      setGroups(view.groups);
      setBaseline(decisionKey(view.groups));
      setSaveState("saved");
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError")) {
        setMessage(errorMessage(error, "변경사항을 저장하지 못했습니다"));
        setSaveState("error");
      }
    } finally {
      if (saveRequest.current === controller) saveRequest.current = null;
    }
  }

  return { groups, loadState, saveState, message, dirty, changeDecision, saveDecisions, retry: () => setReload((value) => value + 1) };
}

function LoadResult({ state, message, retry }: { state: LoadState; message: string; retry: () => void }) {
  if (state === "loading") return <div className="group-loading" role="status">그룹을 판별하고 있습니다…</div>;
  if (state !== "error") return null;
  return <div className="group-error" role="alert">
    <strong>그룹 정보를 불러오지 못했습니다</strong><span>{message}</span>
    <button type="button" className="text-button" onClick={retry}>다시 불러오기</button>
  </div>;
}

export default function GroupReview({ jobId, onComplete }: { jobId: string; onComplete: (jobId: string) => void }) {
  const review = useGroupReview(jobId);
  const [columnsReady, setColumnsReady] = useState(false);

  if (review.loadState !== "ready") {
    return <LoadResult state={review.loadState} message={review.message} retry={review.retry} />;
  }

  return (
    <section className="group-review" aria-labelledby="group-review-title">
      <div className="group-review__intro">
        <span className="eyebrow">2단계 · 폴더 구성 확인</span>
        <h3 id="group-review-title">자동으로 묶인 파일 그룹을 확인하세요</h3>
        <p>같은 컬럼 구조의 파일은 병합이 추천됩니다.</p>
      </div>
      {!review.groups.length && <div className="group-empty">표시할 데이터 그룹이 없습니다.</div>}
      <div className="group-list">
        {review.groups.map((group) => (
          <GroupCard
            key={group.group_id}
            group={group}
            disabled={review.saveState === "saving"}
            onChange={(merge) => review.changeDecision(group.group_id, merge)}
          />
        ))}
      </div>
      {!!review.groups.length && (
        <div className="group-save">
          <span className={`group-save__message group-save__message--${review.saveState}`} aria-live="polite">
            {review.saveState === "saved" && "변경사항을 저장했습니다."}
            {review.saveState === "error" && review.message}
            {review.dirty && review.saveState === "idle" && "저장하지 않은 변경사항이 있습니다."}
          </span>
          <button type="button" className="upload-button" disabled={!review.dirty || review.saveState === "saving"} onClick={() => { void review.saveDecisions(); }}>
            {review.saveState === "saving" ? "저장 중…" : "변경사항 저장"}
          </button>
        </div>
      )}
      {!!review.groups.length && (
        <>
          <ColumnReview jobId={jobId} groupIds={review.groups.map((group) => group.group_id)} onReadyChange={setColumnsReady} />
          <RunPanel
            jobId={jobId}
            ready={columnsReady && !review.dirty && review.saveState !== "saving" && review.saveState !== "error"}
            onComplete={onComplete}
          />
        </>
      )}
    </section>
  );
}
