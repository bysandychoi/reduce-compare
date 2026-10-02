import { useState } from "react";

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

export default function GraphExplorer() {
  const [kind, setKind] = useState<GraphKind>("scatter-2d");
  const [mode, setMode] = useState<ViewMode>("side");
  const label = GRAPH_LABELS[kind];
  return <section className="graph-section" aria-labelledby="graph-title">
    <div className="graph-heading">
      <div><span>시각적 비교</span><h4 id="graph-title">원본과 축소본 그래프</h4></div>
      <div className="graph-controls">
        <label>그래프 종류<select value={kind} onChange={(event) => setKind(event.target.value as GraphKind)}>
          {Object.entries(GRAPH_LABELS).map(([value, text]) => <option key={value} value={value}>{text}</option>)}
        </select></label>
        <fieldset><legend>보기 방식</legend>
          <button type="button" aria-pressed={mode === "side"} onClick={() => setMode("side")}>나란히</button>
          <button type="button" aria-pressed={mode === "overlay"} onClick={() => setMode("overlay")}>겹쳐보기</button>
        </fieldset>
      </div>
    </div>
    <div className={`graph-stage graph-stage--${mode}`} aria-live="polite">
      {mode === "side" ? <>
        <GraphPlaceholder label={`원본 · ${label}`} /><GraphPlaceholder label={`축소본 · ${label}`} />
      </> : <GraphPlaceholder label={`원본 + 축소본 · ${label}`} />}
    </div>
  </section>;
}
