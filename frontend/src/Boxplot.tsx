import type { BoxSummary, BoxplotData } from "./api/client";

type Source = "original" | "reduced" | "both";

const LEFT = 44;
const RIGHT = 404;
const ROW_HEIGHT = 56;

function label(value: number) {
  if (!Number.isFinite(value)) return "—";
  const absolute = Math.abs(value);
  if (absolute >= 1000 || (absolute > 0 && absolute < 0.01)) return value.toExponential(1);
  return Number(value.toFixed(absolute >= 10 ? 0 : 2)).toString();
}

function Box({ box, y, scale, className }: { box: BoxSummary; y: number; scale: (value: number) => number; className: string }) {
  const half = 13;
  return <g className={className}>
    <line className="box-whisker" x1={scale(box.low_whisker)} x2={scale(box.high_whisker)} y1={y} y2={y} />
    <line className="box-whisker" x1={scale(box.low_whisker)} x2={scale(box.low_whisker)} y1={y - 7} y2={y + 7} />
    <line className="box-whisker" x1={scale(box.high_whisker)} x2={scale(box.high_whisker)} y1={y - 7} y2={y + 7} />
    <rect className="box-body" x={scale(box.q1)} y={y - half} width={Math.max(scale(box.q3) - scale(box.q1), 1)} height={half * 2} />
    <line className="box-median" x1={scale(box.median)} x2={scale(box.median)} y1={y - half} y2={y + half} />
    {box.outliers.map((value, index) => <circle key={index} className="box-outlier" cx={scale(value)} cy={y} r="2.4" />)}
  </g>;
}

export default function Boxplot({ data, source }: { data: BoxplotData; source: Source }) {
  const rows: Array<{ box: BoxSummary; title: string; className: string }> = source === "both"
    ? [{ box: data.original, title: "원본", className: "box--original" }, { box: data.reduced, title: "축소본", className: "box--reduced" }]
    : source === "original"
      ? [{ box: data.original, title: "원본", className: "box--original" }]
      : [{ box: data.reduced, title: "축소본", className: "box--reduced" }];
  // 두 상자를 같은 가로축에 둬야 퍼짐 정도를 비교할 수 있다 (한쪽만 볼 때도 축을 바꾸지 않는다).
  const low = Math.min(data.original.minimum, data.reduced.minimum);
  const high = Math.max(data.original.maximum, data.reduced.maximum);
  const span = high - low || 1;
  const scale = (value: number) => LEFT + ((value - low) / span) * (RIGHT - LEFT);
  const height = rows.length * ROW_HEIGHT + 56;
  return <svg className="boxplot" viewBox={`0 0 420 ${height}`} role="img"
    aria-label={`${data.column} 컬럼의 ${source === "both" ? "원본과 축소본" : rows[0].title} 박스플롯`}>
    {rows.map((row, index) => <g key={row.title}>
      <text className="scatter-label" x="6" y={28 + index * ROW_HEIGHT + 4}>{row.title}</text>
      <Box box={row.box} y={28 + index * ROW_HEIGHT} scale={scale} className={row.className} />
    </g>)}
    <line className="scatter-axis" x1={LEFT} x2={RIGHT} y1={height - 26} y2={height - 26} />
    {/* 사분위수 값은 패널 캡션에 글자로 적는다. 축에 찍으면 상자가 좁을 때 글자가 겹친다. */}
    <text className="scatter-label" x={LEFT} y={height - 12} textAnchor="start">{label(low)}</text>
    <text className="scatter-label" x={RIGHT} y={height - 12} textAnchor="end">{label(high)}</text>
    <text className="scatter-label" x={(LEFT + RIGHT) / 2} y={height - 1} textAnchor="middle">{data.column}</text>
  </svg>;
}
