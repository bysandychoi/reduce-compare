import { useEffect, useMemo, useRef, useState } from "react";

import { ApiError, getColumns, updateColumns, type ColumnChoice } from "./api/client";

type LoadState = "loading" | "ready" | "error";
type SaveState = "idle" | "saving" | "saved" | "error";

function errorMessage(error: unknown, fallback: string) {
  return error instanceof ApiError ? error.message : fallback;
}

function selectionKey(columns: ColumnChoice[], useDefault = false) {
  return columns.filter((column) => useDefault ? column.default_selected : column.selected)
    .map((column) => column.name).join("\u0000");
}

function useColumnGroup(jobId: string, groupId: string) {
  const [columns, setColumns] = useState<ColumnChoice[]>([]);
  const [baseline, setBaseline] = useState("");
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [message, setMessage] = useState("");
  const [reload, setReload] = useState(0);
  const saveRequest = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoadState("loading");
    getColumns(jobId, groupId, { signal: controller.signal }).then((view) => {
      if (controller.signal.aborted) return;
      setColumns(view.columns);
      setBaseline(selectionKey(view.columns));
      setLoadState("ready");
      setSaveState("idle");
      setMessage("");
    }).catch((error: unknown) => {
      if (controller.signal.aborted) return;
      setMessage(errorMessage(error, "컬럼 정보를 불러오지 못했습니다"));
      setLoadState("error");
    });
    return () => controller.abort();
  }, [groupId, jobId, reload]);

  useEffect(() => () => saveRequest.current?.abort(), [groupId, jobId]);

  const selected = useMemo(() => columns.filter((column) => column.selected).map((column) => column.name), [columns]);
  const dirty = selectionKey(columns) !== baseline;
  const recommended = selectionKey(columns, true) === selectionKey(columns);

  function edit(next: ColumnChoice[]) {
    setColumns(next);
    setSaveState("idle");
    setMessage("");
  }

  async function save() {
    if (!selected.length || !dirty || saveRequest.current) return;
    const controller = new AbortController();
    saveRequest.current = controller;
    setSaveState("saving");
    setMessage("");
    try {
      const view = await updateColumns(jobId, groupId, { selected }, { signal: controller.signal });
      if (saveRequest.current !== controller) return;
      setColumns(view.columns);
      setBaseline(selectionKey(view.columns));
      setSaveState("saved");
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError")) {
        setMessage(errorMessage(error, "컬럼 선택을 저장하지 못했습니다"));
        setSaveState("error");
      }
    } finally {
      if (saveRequest.current === controller) saveRequest.current = null;
    }
  }

  return { columns, selected, dirty, recommended, loadState, saveState, message, edit, save, retry: () => setReload((value) => value + 1) };
}

function ColumnRow({ column, inputId, disabled, onChange }: { column: ColumnChoice; inputId: string; disabled: boolean; onChange: () => void }) {
  const missing = `${Math.round(column.missing_ratio * 100)}% 결측`;
  return <li className={!column.default_selected ? "column-row column-row--excluded" : "column-row"}>
    <input id={inputId} type="checkbox" checked={column.selected} disabled={disabled} onChange={onChange} />
    <label htmlFor={inputId}>
      <strong>{column.name}</strong>
      <span className="column-badge">{column.kind} · {column.dtype}</span>
      <span className="column-missing">{missing}</span>
      {column.reason && <span className="column-reason">자동 제외 · {column.reason}</span>}
    </label>
  </li>;
}

function ColumnGroup({ jobId, groupId }: { jobId: string; groupId: string }) {
  const review = useColumnGroup(jobId, groupId);
  const title = groupId.replace(/^group-/, "그룹 ");
  if (review.loadState === "loading") return <article className="column-panel column-panel--status" role="status">{title} 컬럼을 불러오고 있습니다…</article>;
  if (review.loadState === "error") return <article className="column-panel column-panel--error" role="alert">
    <strong>{title} 컬럼을 불러오지 못했습니다</strong><span>{review.message}</span>
    <button type="button" className="text-button" onClick={review.retry}>다시 불러오기</button>
  </article>;

  const busy = review.saveState === "saving";
  function toggle(index: number) {
    review.edit(review.columns.map((column, position) => position === index ? { ...column, selected: !column.selected } : column));
  }
  function restore() {
    review.edit(review.columns.map((column) => ({ ...column, selected: column.default_selected })));
  }

  return <article className="column-panel">
    <div className="column-panel__header">
      <h4>{title}</h4><strong>{review.selected.length} / {review.columns.length}개 선택</strong>
    </div>
    {!review.columns.length && <p className="column-empty">선택할 수 있는 컬럼이 없습니다.</p>}
    <ul className="column-options">
      {review.columns.map((column, index) => <ColumnRow key={column.name} column={column} inputId={`column-${groupId}-${index}`} disabled={busy} onChange={() => toggle(index)} />)}
    </ul>
    {!review.selected.length && <p className="column-warning" role="alert">축소를 실행하려면 컬럼을 1개 이상 선택하세요.</p>}
    <div className="column-panel__actions">
      <span className={`column-save-message column-save-message--${review.saveState}`} aria-live="polite">
        {review.saveState === "saved" && "선택을 저장했습니다."}
        {review.saveState === "error" && review.message}
        {review.dirty && review.saveState === "idle" && "저장하지 않은 변경사항이 있습니다."}
      </span>
      <button type="button" className="secondary-button" disabled={review.recommended || busy} onClick={restore}>추천값으로 되돌리기</button>
      <button type="button" className="upload-button" disabled={!review.selected.length || !review.dirty || busy} onClick={() => { void review.save(); }}>
        {busy ? "저장 중…" : "선택 저장"}
      </button>
    </div>
  </article>;
}

export default function ColumnReview({ jobId, groupIds }: { jobId: string; groupIds: string[] }) {
  return <section className="column-review" aria-labelledby="column-review-title">
    <div className="column-review__intro">
      <span className="eyebrow">3단계 · 축소 기준 컬럼</span>
      <h3 id="column-review-title">분석에 사용할 컬럼을 선택하세요</h3>
      <p>선택하지 않은 컬럼도 결과 CSV에는 그대로 포함됩니다.</p>
    </div>
    <div className="column-panel-list">
      {groupIds.map((groupId) => <ColumnGroup key={groupId} jobId={jobId} groupId={groupId} />)}
    </div>
  </section>;
}
