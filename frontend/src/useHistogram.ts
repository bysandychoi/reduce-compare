import { useEffect, useState } from "react";

import { ApiError, getHistogram, type HistogramData } from "./api/client";

type State = { data?: HistogramData; error?: string; loading: boolean };

/** 선택한 컬럼의 분포를 불러온다. 컬럼을 바꾸면 즉시 다시 요청한다. */
export default function useHistogram(jobId: string, groupName: string, active: boolean) {
  // 그룹이 바뀌면 같은 렌더에서 컬럼이 초기화되도록 그룹과 함께 들고 있는다 (요청이 두 번 나가지 않게).
  const [picked, setPicked] = useState<{ group: string; column: string }>({ group: groupName, column: "" });
  const column = picked.group === groupName ? picked.column : "";
  const [state, setState] = useState<State>({ loading: true });

  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    setState((previous) => ({ ...previous, loading: true, error: undefined }));
    getHistogram(jobId, { group: groupName, column: column || undefined }, { signal: controller.signal })
      .then((data) => setState({ data, loading: false }))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setState((previous) => ({ ...previous, loading: false, error: error instanceof ApiError ? error.message : "분포 데이터를 불러오지 못했습니다" }));
      });
    return () => controller.abort();
  }, [active, column, groupName, jobId]);

  // 요청은 useEffect라 한 프레임 늦으므로, 고른 컬럼과 받은 컬럼이 다르면 그때 바로 감춘다.
  const stale = !!column && state.data?.column !== column;
  return {
    ...state,
    column,
    setColumn: (value: string) => setPicked({ group: groupName, column: value }),
    shown: active && !state.loading && !state.error && !stale ? state.data : undefined,
  };
}
