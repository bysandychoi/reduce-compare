import { useEffect, useRef } from "react";

import type { VisualizationData } from "./api/client";
import type { PlotElement } from "plotly.js-dist-min";

function trace(points: number[][], name: string, color: string) {
  return {
    type: "scatter3d", mode: "markers", name,
    x: points.map((point) => point[0]), y: points.map((point) => point[1]),
    z: points.map((point) => point[2]), marker: { color, size: 2.5, opacity: .62 },
    hovertemplate: `${name}<br>x=%{x:.2f}<br>y=%{y:.2f}<br>z=%{z:.2f}<extra></extra>`,
  };
}

function layout(title: string, method: string) {
  const axis = (number: number) => ({ title: `${method} ${number}`, showbackground: false });
  return {
    title: { text: title, x: .03, font: { size: 14 } }, margin: { l: 0, r: 0, t: 42, b: 0 },
    paper_bgcolor: "#fff", plot_bgcolor: "#fff", showlegend: true,
    scene: { xaxis: axis(1), yaxis: axis(2), zaxis: axis(3), aspectmode: "cube" },
  };
}

export default function ThreeDScatter({ data, mode, originalColor, reducedColor }: {
  data: VisualizationData; mode: "side" | "overlay"; originalColor: string; reducedColor: string;
}) {
  const original = useRef<HTMLDivElement>(null);
  const reduced = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let cancelled = false;
    const plots: PlotElement[] = [];
    void import("plotly.js-dist-min").then(async ({ default: Plotly }) => {
      if (cancelled || !original.current) return;
      const method = data.projection_method.toUpperCase();
      const config = { responsive: true, displaylogo: false };
      if (mode === "overlay") {
        plots.push(await Plotly.newPlot(original.current as PlotElement, [
          trace(data.original_points, "원본", originalColor), trace(data.reduced_points, "축소본", reducedColor),
        ], layout("원본 + 축소본", method), config));
        return;
      }
      if (!reduced.current) return;
      const left = await Plotly.newPlot(original.current as PlotElement, [trace(data.original_points, "원본", originalColor)], layout("원본", method), config);
      const right = await Plotly.newPlot(reduced.current as PlotElement, [trace(data.reduced_points, "축소본", reducedColor)], layout("축소본", method), config);
      plots.push(left, right);
      let syncing = false;
      const connect = (source: PlotElement, target: PlotElement) => source.on("plotly_relayout", (update) => {
        const camera = update["scene.camera"];
        if (!camera || syncing) return;
        syncing = true;
        void Plotly.relayout(target, { "scene.camera": camera }).finally(() => { syncing = false; });
      });
      connect(left, right); connect(right, left);
    });
    return () => {
      cancelled = true;
      void import("plotly.js-dist-min").then(({ default: Plotly }) => plots.forEach((plot) => Plotly.purge(plot)));
    };
  }, [data, mode, originalColor, reducedColor]);
  return <>{<div className="scatter-3d" ref={original} />}{mode === "side" && <div className="scatter-3d" ref={reduced} />}</>;
}
