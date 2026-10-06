import { useState, type Dispatch, type SetStateAction } from "react";

import { getBoxplot, getCategoryRatios, getHistogram, type BoxSummary, type BoxplotData, type CategoryRatioData, type GroupResult, type HistogramData, type ProjectionMethod, type VisualizationData } from "./api/client";
import Boxplot from "./Boxplot";
import CategoryRatio from "./CategoryRatio";
import CorrelationHeatmaps from "./CorrelationHeatmaps";
import CorrelationNetworks from "./CorrelationNetworks";
import GraphAxisControls from "./GraphAxisControls";
import GraphSettingsPanel from "./GraphSettingsPanel";
import Histogram from "./Histogram";
import ScatterPlot from "./ScatterPlot";
import ThreeDScatter from "./ThreeDScatter";
import useColumnGraph from "./useColumnGraph";
import useAxisCompatibility from "./useAxisCompatibility";
import useVisualization from "./useVisualization";
import { defaultGraphSettings, type GraphKind, type GraphSettingValue, type GraphSettings } from "./graphSettings";
import type { NetworkLayout } from "./networkLayout";

type ViewMode = "side" | "overlay";

const GRAPH_LABELS: Record<GraphKind, string> = {
  "scatter-2d": "2D 산점도",
  "scatter-3d": "3D 산점도",
  histogram: "히스토그램",
  boxplot: "박스플롯",
  "category-ratio": "범주 비율",
  "correlation-heatmap": "상관 히트맵",
  network: "상관 네트워크",
};

function GraphPlaceholder({ label }: { label: string }) {
  return <div className="graph-placeholder">
    <span aria-hidden="true">⌁</span><strong>{label}</strong><small>그래프 렌더러 연결 영역</small>
  </div>;
}

type ColumnGraphData = HistogramData | BoxplotData | CategoryRatioData;

function numericAxisColumns(group: GroupResult) {
  const columns: unknown = group.detail.columns;
  if (!Array.isArray(columns)) return [];
  return columns.flatMap((column: unknown) => {
    if (typeof column !== "object" || column === null) return [];
    const item = column as { name?: unknown; kind?: unknown };
    return item.kind === "numeric" && typeof item.name === "string" ? [item.name] : [];
  });
}

function restoreGraphDefaults(settings: Dispatch<SetStateAction<GraphSettings>>,
  axes: Array<Dispatch<SetStateAction<string>>>, projection: Dispatch<SetStateAction<ProjectionMethod>>,
  method: ProjectionMethod) {
  settings(defaultGraphSettings());
  axes.forEach((setAxis, index) => setAxis(`projection:${index}`));
  projection(method);
}

// 소수부 6자리를 항상 남긴다 (정수부 자릿수 + 6을 유효숫자로 준다).
// 소수점 자리로 자르면 위도 세 칸이 37.56/37.57/37.57로 뭉개지고,
// 유효숫자를 고정하면 정수부가 커질수록 소수부가 깎여 경도(127.025…) 여섯 칸이 같아진다.
function number(value: number) {
  if (!Number.isFinite(value)) return "—";
  const size = Math.abs(value);
  if (size !== 0 && size < 1e-4) return Number(value.toPrecision(6)).toExponential();
  const whole = size >= 1 ? Math.floor(Math.log10(size)) + 1 : 0;
  return value.toLocaleString(undefined, { maximumSignificantDigits: Math.min(21, whole + 6) });
}

function boxCaption(box: BoxSummary) {
  const shown = box.outliers.length < box.outlier_count
    ? `이상치 ${box.outlier_count.toLocaleString()}개 중 ${box.outliers.length}개 표시`
    : `이상치 ${box.outlier_count.toLocaleString()}개`;
  // 사분위수를 글자로 적는다 — 상자가 좁으면 축 눈금으로는 읽을 수 없다.
  return `${box.rows.toLocaleString()}행 · Q1 ${number(box.q1)} · 중앙값 ${number(box.median)} · Q3 ${number(box.q3)} · ${shown}`;
}

function BoxplotPanel({ data, source, title, originalColor, reducedColor }: { data: BoxplotData; source: "original" | "reduced" | "both"; title: string; originalColor: string; reducedColor: string }) {
  const caption = source === "both"
    ? `원본 ${boxCaption(data.original)} / 축소본 ${boxCaption(data.reduced)}`
    : boxCaption(source === "reduced" ? data.reduced : data.original);
  return <div className="scatter-panel"><div><strong>{title}</strong><span>{caption}</span></div><Boxplot data={data} source={source} originalColor={originalColor} reducedColor={reducedColor} /></div>;
}

function ColumnGraphNotes({ data }: { data: ColumnGraphData }) {
  return <>
    {!data.weighted && <p className="graph-note">대표 행 가중치를 쓸 수 없어 모든 대표 행을 같은 비중으로 셌습니다. 지표 표의 분포 점수와 다를 수 있습니다.</p>}
    {data.dropped_original > 0 && <p className="graph-note">원본에서 {data.dropped_original.toLocaleString()}행을 뺐습니다 (축소 대상이 아니었거나 값이 결측·무한대).</p>}
    {data.dropped_reduced > 0 && <p className="graph-note">축소본에서 값이 결측·무한대인 {data.dropped_reduced.toLocaleString()}행을 뺐습니다.</p>}
  </>;
}

function HistogramPanel({ data, source, title, originalColor, reducedColor }: { data: HistogramData; source: "original" | "reduced" | "both"; title: string; originalColor: string; reducedColor: string }) {
  const rows = source === "reduced" ? data.reduced_rows
    : source === "original" ? data.original_rows : data.original_rows + data.reduced_rows;
  return <div className="scatter-panel"><div><strong>{title}</strong><span>{rows.toLocaleString()}행</span></div><Histogram data={data} source={source} originalColor={originalColor} reducedColor={reducedColor} /></div>;
}

function CategoryPanel({ data, source, title, originalColor, reducedColor }: { data: CategoryRatioData; source: "original" | "reduced" | "both"; title: string; originalColor: string; reducedColor: string }) {
  const rows = source === "reduced" ? data.reduced_rows
    : source === "original" ? data.original_rows : data.original_rows + data.reduced_rows;
  return <div className="scatter-panel"><div><strong>{title}</strong><span>{rows.toLocaleString()}행</span></div><CategoryRatio data={data} source={source} originalColor={originalColor} reducedColor={reducedColor} /></div>;
}

function ScatterPanel({ data, source, title, originalColor, reducedColor, pointSize, opacity, weightByRepresentative }: {
  data: VisualizationData; source: "original" | "reduced" | "both"; title: string; originalColor: string; reducedColor: string;
  pointSize: number; opacity: number; weightByRepresentative: boolean;
}) {
  return <div className="scatter-panel"><div><strong>{title}</strong><span>{source === "original" ? data.original_points.length : source === "reduced" ? data.reduced_points.length : data.original_points.length + data.reduced_points.length}개 점</span></div><ScatterPlot data={data} source={source} originalColor={originalColor} reducedColor={reducedColor} pointSize={pointSize} opacity={opacity} weightByRepresentative={weightByRepresentative} /></div>;
}

export default function GraphExplorer({ jobId, group }: { jobId: string; group: GroupResult }) {
  const [kind, setKind] = useState<GraphKind>("scatter-2d");
  const [mode, setMode] = useState<ViewMode>("side");
  const [settings, setSettings] = useState(defaultGraphSettings);
  const [xAxis, setXAxis] = useState("projection:0");
  const [yAxis, setYAxis] = useState("projection:1");
  const [zAxis, setZAxis] = useState("projection:2");
  const setGraphSetting = (key: string, value: GraphSettingValue) => setSettings((current) => {
    if (key === "palette") {
      const colors = value === "colorblind" ? ["#0072B2", "#D55E00"]
        : value === "high-contrast" ? ["#111111", "#E69F00"] : ["#7c8794", "#176b9b"];
      return { ...current, palette: value, originalColor: colors[0], reducedColor: colors[1] };
    }
    return { ...current, [key]: value, ...(key === "originalColor" || key === "reducedColor" ? { palette: "custom" } : {}) };
  });
  const resetSettings = () => restoreGraphDefaults(setSettings, [setXAxis, setYAxis, setZAxis], setProjection, group.projection.method as ProjectionMethod);
  const [projection, setProjection] = useState<ProjectionMethod>(group.projection.method as ProjectionMethod);
  const visual = useVisualization(jobId, group, kind, projection, xAxis, yAxis, zAxis);
  const histogram = useColumnGraph(getHistogram, jobId, group.name, kind === "histogram");
  const boxplot = useColumnGraph(getBoxplot, jobId, group.name, kind === "boxplot");
  const category = useColumnGraph(getCategoryRatios, jobId, group.name, kind === "category-ratio");
  const graph = kind === "boxplot" ? boxplot : kind === "category-ratio" ? category : histogram;
  const label = GRAPH_LABELS[kind];
  const axisColumns = numericAxisColumns(group);
  useAxisCompatibility(axisColumns, xAxis, yAxis, zAxis, setXAxis, setYAxis, setZAxis);
  const pointSize = Number(settings.pointSize);
  const opacity = Number(settings.opacity);
  const weightByRepresentative = Boolean(settings.weightPointSize);
  const byColumn = kind === "histogram" || kind === "boxplot" || kind === "category-ratio";
  const shown: ColumnGraphData | undefined = graph.shown;
  return <section className="graph-section" aria-labelledby="graph-title">
    <div className="graph-heading">
      <div><span>시각적 비교</span><h4 id="graph-title">원본과 축소본 그래프</h4></div>
      <div className="graph-controls">
        <label>그래프 종류<select value={kind} onChange={(event) => {
          const next = event.target.value as GraphKind;
          setKind(next);
          if (next === "scatter-2d") {
            if (xAxis === "projection:2") setXAxis("projection:0");
            if (yAxis === "projection:2") setYAxis("projection:1");
          }
        }}>
          {Object.entries(GRAPH_LABELS).map(([value, text]) => <option key={value} value={value}>{text}</option>)}
        </select></label>
        {(kind === "scatter-2d" || kind === "scatter-3d") && <label>투영 방식<select value={projection} onChange={(event) => setProjection(event.target.value as ProjectionMethod)}><option value="pca">PCA</option><option value="umap">UMAP</option></select></label>}
        {(kind === "scatter-2d" || kind === "scatter-3d") && <GraphAxisControls kind={kind} projection={projection} columns={axisColumns} xAxis={xAxis} yAxis={yAxis} zAxis={zAxis} onXAxis={setXAxis} onYAxis={setYAxis} onZAxis={setZAxis} />}
        {byColumn && graph.data && <label>컬럼<select value={graph.column || graph.data.column} onChange={(event) => graph.setColumn(event.target.value)}>
          {graph.data.columns.map((name) => <option key={name} value={name}>{name}</option>)}
        </select></label>}
        {kind !== "correlation-heatmap" && kind !== "network" && <fieldset><legend>보기 방식</legend>
          <button type="button" aria-pressed={mode === "side"} onClick={() => setMode("side")}>나란히</button>
          <button type="button" aria-pressed={mode === "overlay"} onClick={() => setMode("overlay")}>겹쳐보기</button>
        </fieldset>}
      </div>
    </div>
    <GraphSettingsPanel graph={kind} settings={settings} onChange={setGraphSetting} onReset={resetSettings} />
    {shown && <ColumnGraphNotes data={shown} />}
    <div className={`graph-stage graph-stage--${mode}`} aria-live="polite" aria-busy={byColumn ? graph.loading : kind === "scatter-2d" || kind === "scatter-3d" ? visual.loading : undefined}>
      {(kind === "scatter-2d" || kind === "scatter-3d") && visual.loading && <p className="graph-message">{projection.toUpperCase()} 좌표를 준비하고 있습니다…</p>}
      {(kind === "scatter-2d" || kind === "scatter-3d") && visual.error && <p className="graph-message graph-message--error">{visual.error}</p>}
      {kind === "scatter-2d" && visual.data && (mode === "side" ? <><ScatterPanel data={visual.data} source="original" title="원본" originalColor={String(settings.originalColor)} reducedColor={String(settings.reducedColor)} pointSize={pointSize} opacity={opacity} weightByRepresentative={weightByRepresentative} /><ScatterPanel data={visual.data} source="reduced" title="축소본" originalColor={String(settings.originalColor)} reducedColor={String(settings.reducedColor)} pointSize={pointSize} opacity={opacity} weightByRepresentative={weightByRepresentative} /></> : <ScatterPanel data={visual.data} source="both" title="원본 + 축소본" originalColor={String(settings.originalColor)} reducedColor={String(settings.reducedColor)} pointSize={pointSize} opacity={opacity} weightByRepresentative={weightByRepresentative} />)}
      {kind === "scatter-3d" && visual.data && <ThreeDScatter data={visual.data} mode={mode} originalColor={String(settings.originalColor)} reducedColor={String(settings.reducedColor)} pointSize={pointSize} opacity={opacity} weightByRepresentative={weightByRepresentative} />}
      {byColumn && graph.loading && <p className="graph-message">{label}을(를) 계산하고 있습니다…</p>}
      {byColumn && graph.error && <p className="graph-message graph-message--error">{graph.error}</p>}
      {shown && "edges" in shown && (mode === "side"
        ? <><HistogramPanel data={shown} source="original" title="원본" originalColor={String(settings.originalColor)} reducedColor={String(settings.reducedColor)} /><HistogramPanel data={shown} source="reduced" title="축소본" originalColor={String(settings.originalColor)} reducedColor={String(settings.reducedColor)} /></>
        : <HistogramPanel data={shown} source="both" title="원본 + 축소본" originalColor={String(settings.originalColor)} reducedColor={String(settings.reducedColor)} />)}
      {shown && "categories" in shown && (mode === "side"
        ? <><CategoryPanel data={shown} source="original" title="원본" originalColor={String(settings.originalColor)} reducedColor={String(settings.reducedColor)} /><CategoryPanel data={shown} source="reduced" title="축소본" originalColor={String(settings.originalColor)} reducedColor={String(settings.reducedColor)} /></>
        : <CategoryPanel data={shown} source="both" title="원본 + 축소본" originalColor={String(settings.originalColor)} reducedColor={String(settings.reducedColor)} />)}
      {shown && !("edges" in shown) && !("categories" in shown) && (mode === "side"
        ? <><BoxplotPanel data={shown} source="original" title="원본" originalColor={String(settings.originalColor)} reducedColor={String(settings.reducedColor)} /><BoxplotPanel data={shown} source="reduced" title="축소본" originalColor={String(settings.originalColor)} reducedColor={String(settings.reducedColor)} /></>
        : <BoxplotPanel data={shown} source="both" title="원본 + 축소본" originalColor={String(settings.originalColor)} reducedColor={String(settings.reducedColor)} />)}
      {kind === "correlation-heatmap" && <CorrelationHeatmaps group={group} />}
      {kind === "network" && <CorrelationNetworks jobId={jobId} group={group.name}
        threshold={Number(settings.correlationThreshold)} layout={settings.networkLayout as NetworkLayout} />}
      {kind !== "scatter-2d" && kind !== "scatter-3d" && kind !== "correlation-heatmap" && kind !== "network" && !byColumn && (mode === "side" ? <><GraphPlaceholder label={`원본 · ${label}`} /><GraphPlaceholder label={`축소본 · ${label}`} /></> : <GraphPlaceholder label={`원본 + 축소본 · ${label}`} />)}
    </div>
  </section>;
}
