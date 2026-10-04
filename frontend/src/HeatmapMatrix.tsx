import { useId } from "react";

import { correlationColor } from "./correlationHeatmap";

type Props = {
  columns: string[];
  matrix: number[][];
  undefinedCells: boolean[][];
  title: string;
  limit: number;
  signed?: boolean;
};

const CELL = 42;
const LEFT = 96;
const TOP = 82;

function short(value: string) {
  return value.length > 13 ? `${value.slice(0, 12)}…` : value;
}

export default function HeatmapMatrix({ columns, matrix, undefinedCells, title, limit, signed = false }: Props) {
  const pattern = useId().replaceAll(":", "");
  const width = LEFT + columns.length * CELL + 16;
  const height = TOP + columns.length * CELL + 16;
  return <section className="heatmap-panel">
    <strong>{title}</strong>
    <div className="heatmap-scroll">
      <svg className="heatmap" viewBox={`0 0 ${width} ${height}`} style={{ minWidth: width }} role="img" aria-label={title}>
        <defs><pattern id={pattern} width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width="8" height="8" fill="#d9dde1" /><line x1="0" y1="0" x2="0" y2="8" stroke="#89939d" strokeWidth="3" />
        </pattern></defs>
        {columns.map((column, index) => <g key={column}>
          <text className="heatmap-label" x={LEFT - 7} y={TOP + index * CELL + CELL / 2 + 4} textAnchor="end"><title>{column}</title>{short(column)}</text>
          <text className="heatmap-label" transform={`translate(${LEFT + index * CELL + CELL / 2} ${TOP - 7}) rotate(-45)`} textAnchor="start"><title>{column}</title>{short(column)}</text>
        </g>)}
        {matrix.flatMap((row, i) => row.map((value, j) => {
          const missing = undefinedCells[i][j];
          const shown = signed ? `${value >= 0 ? "+" : ""}${value.toFixed(2)}` : value.toFixed(2);
          const strong = !missing && limit > 0 && Math.abs(value) / limit >= .55;
          return <g key={`${i}-${j}`}>
            <rect className="heatmap-cell" x={LEFT + j * CELL} y={TOP + i * CELL} width={CELL} height={CELL}
              fill={missing ? `url(#${pattern})` : correlationColor(value, limit)}>
              <title>{columns[i]} × {columns[j]} · {missing ? "측정 불가" : shown}</title>
            </rect>
            <text className={`heatmap-value${strong ? " heatmap-value--light" : ""}`} x={LEFT + j * CELL + CELL / 2} y={TOP + i * CELL + CELL / 2 + 4} textAnchor="middle">{missing ? "—" : shown}</text>
          </g>;
        }))}
      </svg>
    </div>
  </section>;
}
