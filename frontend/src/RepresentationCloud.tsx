import { useEffect, useState } from "react";

import { ApiError, getReport } from "./api/client";
import type { RepresentationReport } from "./reportTypes";
import { clusterColor } from "./clusterColors";

type Bounds = { minX: number; maxX: number; minY: number; maxY: number };

function pointBounds(report: RepresentationReport): Bounds {
  const points = [...report.points.original, ...report.points.reduced];
  const xs = points.map((point) => point[0]);
  const ys = points.map((point) => point[1]);
  const minX = Math.min(...xs, 0), maxX = Math.max(...xs, 1);
  const minY = Math.min(...ys, 0), maxY = Math.max(...ys, 1);
  const padX = Math.max((maxX - minX) * .06, .1);
  const padY = Math.max((maxY - minY) * .06, .1);
  return { minX: minX - padX, maxX: maxX + padX, minY: minY - padY, maxY: maxY + padY };
}

function Cloud({ title, points, clusters, outliers, area }: {
  title: string; points: number[][]; clusters: number[]; outliers: boolean[]; area: Bounds;
}) {
  const x = (value: number) => 26 + (value - area.minX) / (area.maxX - area.minX) * 368;
  const y = (value: number) => 226 - (value - area.minY) / (area.maxY - area.minY) * 190;
  return <div className="report-cloud"><strong>{title}</strong>
    <svg viewBox="0 0 420 250" role="img" aria-label={title + " 군집별 점 구름"}>
      <line x1="26" x2="394" y1="226" y2="226" />
      <line x1="26" x2="26" y1="36" y2="226" />
      {points.map((point, index) => <circle key={index}
        cx={x(point[0])} cy={y(point[1])} r={outliers[index] ? 4.6 : 2.8}
        fill={clusterColor(clusters[index] ?? 0)}
        className={outliers[index] ? "report-cloud__outlier" : undefined}>
        <title>군집 C{(clusters[index] ?? 0) + 1}{outliers[index] ? " · 이상치" : ""}</title>
      </circle>)}
    </svg>
  </div>;
}

function ReportView({ report }: { report: RepresentationReport }) {
  const area = pointBounds(report);
  const clusters = [...new Set([
    ...report.point_metadata.original_clusters, ...report.point_metadata.reduced_clusters,
  ])].sort((a, b) => a - b);
  const ratio = report.size.original_rows / report.size.reduced_rows;
  return <section className="representation" aria-labelledby="representation-title">
    <div className="representation__heading"><div><span>반영 리포트</span>
      <h4 id="representation-title">규모와 분포 비교</h4></div>
      <p>같은 투영 공간과 군집 색으로 원본·축소본을 비교합니다.</p>
    </div>
    <dl className="representation__stats">
      <div><dt>원본</dt><dd>{report.size.original_rows.toLocaleString()}행</dd></div>
      <div><dt>축소본</dt><dd>{report.size.reduced_rows.toLocaleString()}행</dd></div>
      <div><dt>축소 배율</dt><dd>{ratio.toFixed(1)}×</dd></div>
      <div><dt>대표 1행</dt><dd>{report.size.average_rows_per_representative.toLocaleString()}행</dd></div>
    </dl>
    <div className="representation__clouds">
      <Cloud title="원본 점 구름" points={report.points.original}
        clusters={report.point_metadata.original_clusters}
        outliers={report.point_metadata.original_outliers} area={area} />
      <Cloud title="축소본 점 구름" points={report.points.reduced}
        clusters={report.point_metadata.reduced_clusters}
        outliers={report.point_metadata.reduced_outliers} area={area} />
    </div>
    <div className="representation__legend">
      {clusters.map((cluster) => <span key={cluster}><i style={{ background: clusterColor(cluster) }} />C{cluster + 1}</span>)}
      <span><i className="representation__outlier" />이상치</span>
    </div>
  </section>;
}

export default function RepresentationCloud({ jobId, group }: { jobId: string; group: string }) {
  const [state, setState] = useState<{ report?: RepresentationReport; error?: string }>({});
  useEffect(() => {
    const controller = new AbortController();
    setState({});
    getReport(jobId, group, { signal: controller.signal })
      .then((report) => setState({ report }))
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setState({ error: error instanceof ApiError ? error.message : "반영 리포트를 불러오지 못했습니다" });
        }
      });
    return () => controller.abort();
  }, [group, jobId]);
  if (state.error) return <p className="graph-note" role="alert">반영 리포트 · {state.error}</p>;
  if (!state.report) return <p className="result-loading">반영 리포트를 불러오고 있습니다…</p>;
  return <ReportView report={state.report} />;
}
