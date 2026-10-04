import { useEffect, useState } from "react";

import { ApiError, getCorrelationNetworks, type CorrelationNetworksData } from "./api/client";
import CorrelationNetwork from "./CorrelationNetwork";
import type { NetworkLayout } from "./networkLayout";

export default function CorrelationNetworks({ jobId, group, threshold, layout }: { jobId: string; group: string; threshold: number; layout: NetworkLayout }) {
  const [state, setState] = useState<{ data?: CorrelationNetworksData; error?: string; loading: boolean }>({ loading: true });
  useEffect(() => {
    const controller = new AbortController();
    setState((previous) => ({ ...previous, loading: true, error: undefined }));
    getCorrelationNetworks(jobId, group, threshold, { signal: controller.signal })
      .then((data) => setState({ data, loading: false }))
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setState((previous) => ({ ...previous, loading: false, error: error instanceof ApiError ? error.message : "상관 네트워크를 불러오지 못했습니다" }));
        }
      });
    return () => controller.abort();
  }, [group, jobId, threshold]);
  return <>
    <div className="network-controls">
      <strong>표시 기준 |r| ≥ {threshold.toFixed(2)}</strong>
      <div className="network-legend">
        <span className="network-legend--positive">양의 관계</span><span className="network-legend--negative">음의 관계</span><span className="network-legend--unique">한쪽에만 있음</span>
      </div>
    </div>
    {state.loading && <p className="graph-message">상관 네트워크를 준비하고 있습니다…</p>}
    {state.error && <p className="graph-message graph-message--error">{state.error}</p>}
    {!state.loading && !state.error && state.data && (state.data.original.nodes.length < 2
      ? <p className="graph-message">상관 네트워크에는 수치형 컬럼이 2개 이상 필요합니다.</p>
      : <div className="network-grid">
          <CorrelationNetwork graph={state.data.original} other={state.data.reduced} title="원본" layout={layout} />
          <CorrelationNetwork graph={state.data.reduced} other={state.data.original} title="축소본" layout={layout} />
        </div>)}
  </>;
}
