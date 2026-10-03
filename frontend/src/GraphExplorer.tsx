import { useEffect, useState } from "react";

import { ApiError, getHistogram, getVisualization, type GroupResult, type HistogramData, type ProjectionMethod, type VisualizationData } from "./api/client";
import Histogram from "./Histogram";
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

function HistogramPanel({ data, source, title }: { data: HistogramData; source: "original" | "reduced" | "both"; title: string }) {
  const rows = source === "reduced" ? data.reduced_rows
    : source === "original" ? data.original_rows : data.original_rows + data.reduced_rows;
  return <div className="scatter-panel"><div><strong>{title}</strong><span>{rows.toLocaleString()}행</span></div><Histogram data={data} source={source} /></div>;
}

function ScatterPanel({ data, source, title }: { data: VisualizationData; source: "original" | "reduced" | "both"; title: string }) {
  return <div className="scatter-panel"><div><strong>{title}</strong><span>{source === "original" ? data.original_points.length : source === "reduced" ? data.reduced_points.length : data.original_points.length + data.reduced_points.length}개 점</span></div><ScatterPlot data={data} source={source} /></div>;
}

export default function GraphExplorer({ jobId, group }: { jobId: string; group: GroupResult }) {
  const [kind, setKind] = useState<GraphKind>("scatter-2d");
  const [mode, setMode] = useState<ViewMode>("side");
  const [projection, setProjection] = useState<ProjectionMethod>(group.projection.method as ProjectionMethod);
  const [visual, setVisual] = useState<{ data?: VisualizationData; error?: string; loading: boolean }>({ loading: true });
  // 그룹이 바뀌면 같은 렌더에서 컬럼이 초기화되도록 그룹과 함께 들고 있는다 (요청이 두 번 나가지 않게).
  const [picked, setPicked] = useState<{ group: string; column: string }>({ group: group.name, column: "" });
  const column = picked.group === group.name ? picked.column : "";
  const setColumn = (value: string) => setPicked({ group: group.name, column: value });
  const [histogram, setHistogram] = useState<{ data?: HistogramData; error?: string; loading: boolean }>({ loading: true });
  useEffect(() => {
    if (kind !== "histogram") return;
    const controller = new AbortController();
    setHistogram((previous) => ({ ...previous, loading: true, error: undefined }));
    getHistogram(jobId, { group: group.name, column: column || undefined }, { signal: controller.signal })
      .then((data) => setHistogram({ data, loading: false }))
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) setHistogram((previous) => ({ ...previous, loading: false, error: error instanceof ApiError ? error.message : "분포 데이터를 불러오지 못했습니다" }));
      });
    return () => controller.abort();
  }, [column, group.name, jobId, kind]);
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
        {kind === "histogram" && histogram.data && <label>컬럼<select value={column || histogram.data.column} onChange={(event) => setColumn(event.target.value)}>
          {histogram.data.columns.map((name) => <option key={name} value={name}>{name}</option>)}
        </select></label>}
        <fieldset><legend>보기 방식</legend>
          <button type="button" aria-pressed={mode === "side"} onClick={() => setMode("side")}>나란히</button>
          <button type="button" aria-pressed={mode === "overlay"} onClick={() => setMode("overlay")}>겹쳐보기</button>
        </fieldset>
      </div>
    </div>
    {kind === "histogram" && histogram.data && !histogram.data.weighted && <p className="graph-note">대표 행 가중치를 쓸 수 없어 모든 대표 행을 같은 비중으로 셌습니다. 지표 표의 분포 점수와 다를 수 있습니다.</p>}
    {kind === "histogram" && histogram.data && histogram.data.dropped_values > 0 && <p className="graph-note">축소 대상이 아니었던 행과 비교할 수 없는 값(결측·무한대) {histogram.data.dropped_values.toLocaleString()}건을 뺐습니다.</p>}
    <div className={`graph-stage graph-stage--${mode}`} aria-live="polite" aria-busy={kind === "histogram" ? histogram.loading : visual.loading}>
      {(kind === "scatter-2d" || kind === "scatter-3d") && visual.loading && <p className="graph-message">{projection.toUpperCase()} 좌표를 준비하고 있습니다…</p>}
      {(kind === "scatter-2d" || kind === "scatter-3d") && visual.error && <p className="graph-message graph-message--error">{visual.error}</p>}
      {kind === "scatter-2d" && visual.data && (mode === "side" ? <><ScatterPanel data={visual.data} source="original" title="원본" /><ScatterPanel data={visual.data} source="reduced" title="축소본" /></> : <ScatterPanel data={visual.data} source="both" title="원본 + 축소본" />)}
      {kind === "scatter-3d" && visual.data && <ThreeDScatter data={visual.data} mode={mode} />}
      {kind === "histogram" && histogram.loading && <p className="graph-message">분포를 계산하고 있습니다…</p>}
      {kind === "histogram" && histogram.error && <p className="graph-message graph-message--error">{histogram.error}</p>}
      {kind === "histogram" && histogram.data && !histogram.error && (mode === "side"
        ? <><HistogramPanel data={histogram.data} source="original" title="원본" /><HistogramPanel data={histogram.data} source="reduced" title="축소본" /></>
        : <HistogramPanel data={histogram.data} source="both" title="원본 + 축소본" />)}
      {kind !== "scatter-2d" && kind !== "scatter-3d" && kind !== "histogram" && (mode === "side" ? <><GraphPlaceholder label={`원본 · ${label}`} /><GraphPlaceholder label={`축소본 · ${label}`} /></> : <GraphPlaceholder label={`원본 + 축소본 · ${label}`} />)}
    </div>
  </section>;
}
