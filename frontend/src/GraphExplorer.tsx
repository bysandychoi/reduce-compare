import { useEffect, useState } from "react";

import { ApiError, getVisualization, type GroupResult, type ProjectionMethod, type VisualizationData } from "./api/client";
import ScatterPlot from "./ScatterPlot";
import ThreeDScatter from "./ThreeDScatter";

type GraphKind = "scatter-2d" | "scatter-3d" | "histogram" | "boxplot" | "network";
type ViewMode = "side" | "overlay";

const GRAPH_LABELS: Record<GraphKind, string> = {
  "scatter-2d": "2D 산점도",
  "scatter-3d": "3D 산점도",
  histogram: "히스토그램",
  boxplot: "박스플롯",
  network: "상관 네트워크",
};

function GraphPlaceholder({ label }: { label: string }) {
  return <div className="graph-placeholder">
    <span aria-hidden="true">⌁</span><strong>{label}</strong><small>그래프 렌더러 연결 영역</small>
  </div>;
}

function ScatterPanel({ data, source, title }: { data: VisualizationData; source: "original" | "reduced" | "both"; title: string }) {
  return <div className="scatter-panel"><div><strong>{title}</strong><span>{source === "original" ? data.original_points.length : source === "reduced" ? data.reduced_points.length : data.original_points.length + data.reduced_points.length}개 점</span></div><ScatterPlot data={data} source={source} /></div>;
}

export default function GraphExplorer({ jobId, group }: { jobId: string; group: GroupResult }) {
  const [kind, setKind] = useState<GraphKind>("scatter-2d");
  const [mode, setMode] = useState<ViewMode>("side");
  const [projection, setProjection] = useState<ProjectionMethod>(group.projection.method as ProjectionMethod);
  const [visual, setVisual] = useState<{ data?: VisualizationData; error?: string; loading: boolean }>({ loading: true });
  useEffect(() => {
    if (kind !== "scatter-2d" && kind !== "scatter-3d") return;
    const controller = new AbortController();
    setVisual({ loading: true });
    getVisualization(jobId, { group: group.name, mode: "sample", max_points: 1500, projection_method: projection, projection_dimensions: kind === "scatter-3d" ? 3 : 2 }, { signal: controller.signal })
      .then((data) => setVisual({ data, loading: false }))
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) setVisual({ loading: false, error: error instanceof ApiError ? error.message : "그래프 데이터를 불러오지 못했습니다" });
      });
    return () => controller.abort();
  }, [group.name, jobId, kind, projection]);
  const label = GRAPH_LABELS[kind];
  return <section className="graph-section" aria-labelledby="graph-title">
    <div className="graph-heading">
      <div><span>시각적 비교</span><h4 id="graph-title">원본과 축소본 그래프</h4></div>
      <div className="graph-controls">
        <label>그래프 종류<select value={kind} onChange={(event) => setKind(event.target.value as GraphKind)}>
          {Object.entries(GRAPH_LABELS).map(([value, text]) => <option key={value} value={value}>{text}</option>)}
        </select></label>
        {(kind === "scatter-2d" || kind === "scatter-3d") && <label>투영 방식<select value={projection} onChange={(event) => setProjection(event.target.value as ProjectionMethod)}><option value="pca">PCA</option><option value="umap">UMAP</option></select></label>}
        <fieldset><legend>보기 방식</legend>
          <button type="button" aria-pressed={mode === "side"} onClick={() => setMode("side")}>나란히</button>
          <button type="button" aria-pressed={mode === "overlay"} onClick={() => setMode("overlay")}>겹쳐보기</button>
        </fieldset>
      </div>
    </div>
    <div className={`graph-stage graph-stage--${mode}`} aria-live="polite" aria-busy={visual.loading}>
      {(kind === "scatter-2d" || kind === "scatter-3d") && visual.loading && <p className="graph-message">{projection.toUpperCase()} 좌표를 준비하고 있습니다…</p>}
      {(kind === "scatter-2d" || kind === "scatter-3d") && visual.error && <p className="graph-message graph-message--error">{visual.error}</p>}
      {kind === "scatter-2d" && visual.data && (mode === "side" ? <><ScatterPanel data={visual.data} source="original" title="원본" /><ScatterPanel data={visual.data} source="reduced" title="축소본" /></> : <ScatterPanel data={visual.data} source="both" title="원본 + 축소본" />)}
      {kind === "scatter-3d" && visual.data && <ThreeDScatter data={visual.data} mode={mode} />}
      {kind !== "scatter-2d" && kind !== "scatter-3d" && (mode === "side" ? <><GraphPlaceholder label={`원본 · ${label}`} /><GraphPlaceholder label={`축소본 · ${label}`} /></> : <GraphPlaceholder label={`원본 + 축소본 · ${label}`} />)}
    </div>
  </section>;
}
