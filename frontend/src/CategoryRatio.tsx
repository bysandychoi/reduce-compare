import type { CategoryRatioData } from "./api/client";

type Source = "original" | "reduced" | "both";
const LEFT = 128;
const WIDTH = 260;

function shortLabel(value: string) {
  return value.length > 18 ? `${value.slice(0, 17)}…` : value;
}

export default function CategoryRatio({ data, source }: { data: CategoryRatioData; source: Source }) {
  const both = source === "both";
  const rowHeight = both ? 42 : 32;
  const top = both ? 48 : 28;
  const height = top + 6 + data.categories.length * rowHeight;
  const series = source === "original"
    ? [{ values: data.original_ratios, className: "category-bar--original", offset: 0 }]
    : source === "reduced"
      ? [{ values: data.reduced_ratios, className: "category-bar--reduced", offset: 0 }]
      : [
          { values: data.original_ratios, className: "category-bar--original", offset: -7 },
          { values: data.reduced_ratios, className: "category-bar--reduced", offset: 7 },
        ];
  return <svg className="category-ratio" viewBox={`0 0 420 ${height}`} role="img"
    aria-label={`${data.column} 범주별 원본과 축소본 비율`}>
    {both && <g className="category-legend">
      <rect className="category-bar--original" x="128" y="14" width="18" height="8" rx="2" />
      <text x="151" y="22">원본</text>
      <rect className="category-bar--reduced" x="194" y="14" width="18" height="8" rx="2" />
      <text x="217" y="22">축소본</text>
    </g>}
    {[0, .25, .5, .75, 1].map((tick) => <g key={tick}>
      <line className="category-grid" x1={LEFT + WIDTH * tick} x2={LEFT + WIDTH * tick} y1={top - 10} y2={height - 16} />
      <text className="scatter-label" x={LEFT + WIDTH * tick} y={top - 16} textAnchor="middle">{tick * 100}%</text>
    </g>)}
    {data.categories.map((category, index) => {
      const center = top + index * rowHeight;
      return <g key={category}>
        <text className="category-label" x={LEFT - 8} y={center + 4} textAnchor="end">
          <title>{category}</title>{shortLabel(category)}
        </text>
        {series.map(({ values, className, offset }) => <g key={className}>
          <rect className={`category-bar ${className}`} x={LEFT} y={center + offset - 5}
            width={Math.max(0, WIDTH * values[index])} height={both ? 10 : 14} rx="2" />
          <text className="category-value" x={LEFT + WIDTH * values[index] + 5} y={center + offset + 4}>
            {(values[index] * 100).toFixed(1)}%
          </text>
        </g>)}
      </g>;
    })}
  </svg>;
}
