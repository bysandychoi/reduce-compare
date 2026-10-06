import type { HistogramData } from "./api/client";

type Source = "original" | "reduced" | "both";

const LEFT = 38;
const RIGHT = 406;
const TOP = 20;
const BOTTOM = 212;

function axisLabel(value: number) {
  if (!Number.isFinite(value)) return "—";
  const absolute = Math.abs(value);
  if (absolute >= 1000 || (absolute > 0 && absolute < 0.01)) return value.toExponential(1);
  return Number(value.toFixed(absolute >= 10 ? 0 : 2)).toString();
}

function BarLayer({ ratios, peak, className, color }: { ratios: number[]; peak: number; className: string; color: string }) {
  const width = (RIGHT - LEFT) / ratios.length;
  return <>{ratios.map((ratio, index) => {
    const height = peak > 0 ? (ratio / peak) * (BOTTOM - TOP) : 0;
    return <rect
      key={index} className={className} x={LEFT + index * width} y={BOTTOM - height}
      width={Math.max(width - 1, 0.6)} height={height} fill={color}
    />;
  })}</>;
}

export default function Histogram({ data, source, originalColor, reducedColor }: {
  data: HistogramData; source: Source; originalColor: string; reducedColor: string;
}) {
  // 세로축은 항상 양쪽 분포를 함께 보고 정한다 — 나란히 볼 때 패널마다 배율이 달라지면 안 된다.
  const peak = Math.max(...data.original_ratios, ...data.reduced_ratios, 0.0001);
  const first = data.edges[0];
  const last = data.edges[data.edges.length - 1];
  const middle = (first + last) / 2;
  return <svg className="histogram" viewBox="0 0 420 250" role="img"
    aria-label={`${data.column} 컬럼의 ${source === "original" ? "원본" : source === "reduced" ? "축소본" : "원본과 축소본"} 분포`}>
    <line className="scatter-axis" x1={LEFT} x2={RIGHT} y1={BOTTOM} y2={BOTTOM} />
    <line className="scatter-axis" x1={LEFT} x2={LEFT} y1={TOP} y2={BOTTOM} />
    {(source === "original" || source === "both") && <BarLayer ratios={data.original_ratios} peak={peak} className="histogram-bar histogram-bar--original" color={originalColor} />}
    {(source === "reduced" || source === "both") && <BarLayer ratios={data.reduced_ratios} peak={peak} className="histogram-bar histogram-bar--reduced" color={reducedColor} />}
    <text className="scatter-label" x={LEFT} y={BOTTOM + 16} textAnchor="start">{axisLabel(first)}</text>
    <text className="scatter-label" x={(LEFT + RIGHT) / 2} y={BOTTOM + 16} textAnchor="middle">{axisLabel(middle)}</text>
    <text className="scatter-label" x={RIGHT} y={BOTTOM + 16} textAnchor="end">{axisLabel(last)}</text>
    <text className="scatter-label" x={(LEFT + RIGHT) / 2} y={BOTTOM + 34} textAnchor="middle">{data.column}</text>
    <text className="scatter-label" x="12" y={(TOP + BOTTOM) / 2} textAnchor="middle"
      transform={`rotate(-90 12 ${(TOP + BOTTOM) / 2})`}>비율</text>
    <text className="scatter-label" x={LEFT - 6} y={TOP + 6} textAnchor="end">{(peak * 100).toFixed(1)}%</text>
  </svg>;
}
