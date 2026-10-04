import type { GroupResult } from "./api/client";
import HeatmapMatrix from "./HeatmapMatrix";
import { parseCorrelationHeatmap } from "./correlationHeatmap";

export default function CorrelationHeatmaps({ group }: { group: GroupResult }) {
  const parsed = parseCorrelationHeatmap(group.detail);
  if ("error" in parsed) return <p className="graph-message graph-message--error">{parsed.error}</p>;
  const data = parsed.data;
  if (data.columns.length < 2) return <p className="graph-message">상관을 비교하려면 수치형 컬럼이 2개 이상 필요합니다.</p>;
  const method = data.method === "spearman" ? "Spearman" : "Pearson";
  return <>
    <div className="heatmap-legend" aria-label="상관행렬 색상 범례">
      <span><i className="heatmap-swatch heatmap-swatch--negative" />음의 상관·차이</span>
      <span><i className="heatmap-swatch heatmap-swatch--zero" />0</span>
      <span><i className="heatmap-swatch heatmap-swatch--positive" />양의 상관·차이</span>
      <span><i className="heatmap-swatch heatmap-swatch--undefined" />측정 불가</span>
      <small>차이 범위 ±{data.differenceLimit.toFixed(2)}</small>
    </div>
    <div className="heatmap-grid">
      <HeatmapMatrix columns={data.columns} matrix={data.original} undefinedCells={data.undefinedOriginal} title={`원본 (${method})`} limit={1} />
      <HeatmapMatrix columns={data.columns} matrix={data.reduced} undefinedCells={data.undefinedReduced} title={`축소본 (${method})`} limit={1} />
      <HeatmapMatrix columns={data.columns} matrix={data.difference} undefinedCells={data.undefinedDifference} title="차이 · 축소본 − 원본" limit={data.differenceLimit} signed />
    </div>
  </>;
}
