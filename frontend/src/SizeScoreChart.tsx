import { useMemo } from "react";

import type { GroupResult, ScorePoint } from "./api/client";

const WIDTH = 720;
const HEIGHT = 300;
const MARGIN = { top: 24, right: 24, bottom: 48, left: 54 };
function nearestPoint(points: ScorePoint[], size: number) {
  return points.reduce((best, point) => (
    Math.abs(point.size - size) < Math.abs(best.size - size) ? point : best
  ));
}

export default function SizeScoreChart({ group, target }: { group: GroupResult; target: number }) {
  const points = useMemo(() => [...group.size_curve].sort((a, b) => a.size - b.size), [group]);
  if (!points.length) return <section className="curve-section" aria-labelledby="curve-title">
    <div className="curve-heading"><div><span>크기 탐색</span><h4 id="curve-title">크기별 종합 점수</h4></div></div>
    <p className="curve-empty">기록된 후보 크기가 없습니다.</p>
  </section>;

  const minSize = points[0].size;
  const maxSize = points.at(-1)?.size ?? minSize;
  const innerWidth = WIDTH - MARGIN.left - MARGIN.right;
  const innerHeight = HEIGHT - MARGIN.top - MARGIN.bottom;
  const x = (size: number) => MARGIN.left + (maxSize === minSize ? innerWidth / 2 : (size - minSize) / (maxSize - minSize) * innerWidth);
  const y = (score: number) => MARGIN.top + (100 - score) / 100 * innerHeight;
  const selected = nearestPoint(points, group.reduced_rows);
  const line = points.map((point) => `${x(point.size)},${y(point.score)}`).join(" ");
  return <section className="curve-section" aria-labelledby="curve-title">
    <div className="curve-heading">
      <div><span>크기 탐색</span><h4 id="curve-title">크기별 종합 점수</h4></div>
      <div className="curve-legend"><span><i />점수</span><span><i />기준 {target}점</span><span><i />선택 {selected.size.toLocaleString()}행</span></div>
    </div>
    <svg className="curve-chart" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-labelledby="curve-svg-title curve-svg-desc">
      <title id="curve-svg-title">후보 축소 크기별 종합 점수 곡선</title>
      <desc id="curve-svg-desc">기준은 {target}점이며 {selected.size}행, {selected.score.toFixed(1)}점이 선택 지점입니다.</desc>
      {[0, 25, 50, 75, 100].map((tick) => <g key={tick}>
        <line className="curve-grid" x1={MARGIN.left} x2={WIDTH - MARGIN.right} y1={y(tick)} y2={y(tick)} />
        <text className="curve-axis" x={MARGIN.left - 10} y={y(tick) + 4} textAnchor="end">{tick}</text>
      </g>)}
      <line className="curve-target" x1={MARGIN.left} x2={WIDTH - MARGIN.right} y1={y(target)} y2={y(target)} />
      {points.length > 1 && <polyline className="curve-line" points={line} />}
      {points.map((point) => <g key={`${point.size}-${point.score}`}>
        <circle className={point === selected ? "curve-point curve-point--selected" : "curve-point"} cx={x(point.size)} cy={y(point.score)} r={point === selected ? 7 : 4} />
        <text className="curve-axis" x={x(point.size)} y={HEIGHT - 20} textAnchor="middle">{point.size.toLocaleString()}</text>
      </g>)}
      <text className="curve-selected-label" x={x(selected.size)} y={Math.max(16, y(selected.score) - 13)} textAnchor="middle">{selected.score.toFixed(1)}점</text>
      <text className="curve-axis-label" x={WIDTH / 2} y={HEIGHT - 2} textAnchor="middle">후보 축소 크기 (행)</text>
    </svg>
  </section>;
}
