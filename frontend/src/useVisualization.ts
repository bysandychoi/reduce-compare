import { useEffect, useState } from "react";

import { ApiError, getVisualization, type GroupResult, type ProjectionMethod, type VisualizationData } from "./api/client";
import type { GraphKind } from "./graphSettings";

export default function useVisualization(
  jobId: string, group: GroupResult, kind: GraphKind, projection: ProjectionMethod,
  xAxis: string, yAxis: string, zAxis: string,
) {
  const [visual, setVisual] = useState<{ data?: VisualizationData; error?: string; loading: boolean }>({ loading: true });
  const zSelection = kind === "scatter-3d" ? zAxis : undefined;
  useEffect(() => {
    if (kind !== "scatter-2d" && kind !== "scatter-3d") return;
    const controller = new AbortController();
    setVisual({ loading: true });
    getVisualization(jobId, {
      group: group.name, mode: "sample", max_points: 1500, projection_method: projection,
      projection_dimensions: kind === "scatter-3d" ? 3 : 2, x_axis: xAxis, y_axis: yAxis,
      ...(zSelection ? { z_axis: zSelection } : {}),
    }, { signal: controller.signal })
      .then((data) => setVisual({ data, loading: false }))
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setVisual({ loading: false, error: error instanceof ApiError ? error.message : "그래프 데이터를 불러오지 못했습니다" });
        }
      });
    return () => controller.abort();
  }, [group.name, jobId, kind, projection, xAxis, yAxis, zSelection]);
  return visual;
}
