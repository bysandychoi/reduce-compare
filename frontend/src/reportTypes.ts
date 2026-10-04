import type { ProjectionData } from "./api/types";

export type ReportPointMetadata = {
  original_clusters: number[];
  reduced_clusters: number[];
  original_outliers: boolean[];
  reduced_outliers: boolean[];
};

export type RepresentationReport = {
  group: string;
  reduction_method: string;
  size: {
    original_rows: number;
    prepared_rows: number;
    reduced_rows: number;
    average_rows_per_representative: number;
  };
  points: ProjectionData;
  point_metadata: ReportPointMetadata;
  cluster_report: Record<string, unknown>;
  relationships: Record<string, unknown>;
};
