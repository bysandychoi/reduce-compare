import type { GraphKind } from "./graphSettings";

type Axis = { key: string; label: string; value: string; onChange: (value: string) => void };

export default function GraphAxisControls({ kind, projection, columns, xAxis, yAxis, zAxis,
  onXAxis, onYAxis, onZAxis }: {
  kind: GraphKind; projection: string; columns: string[]; xAxis: string; yAxis: string; zAxis: string;
  onXAxis: (value: string) => void; onYAxis: (value: string) => void; onZAxis: (value: string) => void;
}) {
  const axes: Axis[] = [
    { key: "x", label: "X축", value: xAxis, onChange: onXAxis },
    { key: "y", label: "Y축", value: yAxis, onChange: onYAxis },
    ...(kind === "scatter-3d" ? [{ key: "z", label: "Z축", value: zAxis, onChange: onZAxis }] : []),
  ];
  return <>{axes.map((axis) => <label key={axis.key}>{axis.label}<select value={axis.value} onChange={(event) => axis.onChange(event.target.value)}>
    <option value="projection:0">{projection.toUpperCase()} 1</option>
    <option value="projection:1">{projection.toUpperCase()} 2</option>
    {kind === "scatter-3d" && <option value="projection:2">{projection.toUpperCase()} 3</option>}
    {columns.map((column) => <option key={column} value={`column:${column}`}>{column}</option>)}
  </select></label>)}</>;
}
