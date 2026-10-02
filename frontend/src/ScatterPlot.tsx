import type { VisualizationData } from "./api/client";

type Bounds = { minX: number; maxX: number; minY: number; maxY: number };

function bounds(data: VisualizationData): Bounds {
  const points = [...data.original_points, ...data.reduced_points].filter((point) => point.length >= 2);
  const xs = points.map((point) => point[0]);
  const ys = points.map((point) => point[1]);
  const minX = Math.min(...xs, 0); const maxX = Math.max(...xs, 1);
  const minY = Math.min(...ys, 0); const maxY = Math.max(...ys, 1);
  const padX = Math.max((maxX - minX) * .05, .1);
  const padY = Math.max((maxY - minY) * .05, .1);
  return { minX: minX - padX, maxX: maxX + padX, minY: minY - padY, maxY: maxY + padY };
}

function PointLayer({ points, area, className }: { points: number[][]; area: Bounds; className: string }) {
  const x = (value: number) => 32 + (value - area.minX) / (area.maxX - area.minX) * 356;
  const y = (value: number) => 226 - (value - area.minY) / (area.maxY - area.minY) * 198;
  return <>{points.map((point, index) => <circle
    key={index} className={className} cx={x(point[0])} cy={y(point[1])} r="2.2"
  />)}</>;
}

export default function ScatterPlot({ data, source }: { data: VisualizationData; source: "original" | "reduced" | "both" }) {
  const area = bounds(data);
  const method = data.projection_method.toUpperCase();
  return <svg className="scatter-plot" viewBox="0 0 420 260" role="img" aria-label={`${method} 2D ${source} 산점도`}>
    <line className="scatter-axis" x1="32" x2="388" y1="226" y2="226" />
    <line className="scatter-axis" x1="32" x2="32" y1="28" y2="226" />
    {(source === "original" || source === "both") && <PointLayer points={data.original_points} area={area} className="scatter-point scatter-point--original" />}
    {(source === "reduced" || source === "both") && <PointLayer points={data.reduced_points} area={area} className="scatter-point scatter-point--reduced" />}
    <text className="scatter-label" x="210" y="252" textAnchor="middle">{method} 1</text>
    <text className="scatter-label" x="12" y="130" textAnchor="middle" transform="rotate(-90 12 130)">{method} 2</text>
  </svg>;
}
