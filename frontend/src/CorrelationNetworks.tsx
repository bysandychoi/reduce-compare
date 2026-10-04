import { useEffect, useState } from "react";

import { ApiError, getCorrelationNetworks, type CorrelationNetworksData } from "./api/client";
import CorrelationNetwork from "./CorrelationNetwork";

export default function CorrelationNetworks({ jobId, group }: { jobId: string; group: string }) {
  const [threshold, setThreshold] = useState(.5);
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
      <label>엣지 임계값 <strong>|r| ≥ {threshold.toFixed(2)}</strong>
        <input type="range" min="0" max="1" step="0.05" value={threshold}
          onChange={(event) => setThreshold(Number(event.target.value))} />
      </label>
      <div className="network-legend">
        <span className="network-legend--positive">양의 관계</span><span className="network-legend--negative">음의 관계</span><span className="network-legend--unique">한쪽에만 있음</span>
      </div>
    </div>
    {state.loading && <p className="graph-message">상관 네트워크를 준비하고 있습니다…</p>}
    {state.error && <p className="graph-message graph-message--error">{state.error}</p>}
    {!state.loading && !state.error && state.data && (state.data.original.nodes.length < 2
      ? <p className="graph-message">상관 네트워크에는 수치형 컬럼이 2개 이상 필요합니다.</p>
      : <div className="network-grid">
          <CorrelationNetwork graph={state.data.original} other={state.data.reduced} title="원본" />
          <CorrelationNetwork graph={state.data.reduced} other={state.data.original} title="축소본" />
        </div>)}
  </>;
}
