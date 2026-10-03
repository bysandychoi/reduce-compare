import { useEffect, useState } from "react";

import { ApiError, type ApiOptions } from "./api/client";

type ColumnView = { column: string; columns: string[] };
type Loader<T> = (jobId: string, view: { group: string; column?: string }, options?: ApiOptions) => Promise<T>;

/** 컬럼 하나를 골라 비교하는 그래프(히스토그램·박스플롯)의 로딩과 컬럼 선택을 맡는다. */
export default function useColumnGraph<T extends ColumnView>(
  load: Loader<T>, jobId: string, groupName: string, active: boolean,
) {
  // 그룹이 바뀌면 같은 렌더에서 컬럼이 초기화되도록 그룹과 함께 들고 있는다 (요청이 두 번 나가지 않게).
  const [picked, setPicked] = useState<{ group: string; column: string }>({ group: groupName, column: "" });
  const column = picked.group === groupName ? picked.column : "";
  const [state, setState] = useState<{ data?: T; error?: string; loading: boolean }>({ loading: true });

  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    setState((previous) => ({ ...previous, loading: true, error: undefined }));
    load(jobId, { group: groupName, column: column || undefined }, { signal: controller.signal })
      .then((data) => setState({ data, loading: false }))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setState((previous) => ({ ...previous, loading: false, error: error instanceof ApiError ? error.message : "그래프 데이터를 불러오지 못했습니다" }));
      });
    return () => controller.abort();
  }, [active, column, groupName, jobId, load]);

  // 요청은 useEffect라 한 프레임 늦으므로, 고른 컬럼과 받은 컬럼이 다르면 그때 바로 감춘다.
  const stale = !!column && state.data?.column !== column;
  return {
    ...state,
    column,
    setColumn: (value: string) => setPicked({ group: groupName, column: value }),
    shown: active && !state.loading && !state.error && !stale ? state.data : undefined,
  };
}
