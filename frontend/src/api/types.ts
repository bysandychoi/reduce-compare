export type ApiOptions = { signal?: AbortSignal };

export type Health = { status: "ok"; version: string };
export type UploadItem = { file: File; path: string };
export type JobCreated = { job_id: string; files: string[] };

export type ColumnView = {
  name: string;
  kind: string;
  dtype: string;
  missing_ratio: number;
  selected: boolean;
  reason: string;
};

export type GroupView = {
  group_id: string;
  files: string[];
  columns: ColumnView[];
  merge: boolean;
};

export type GroupsView = { groups: GroupView[] };
export type GroupDecision = { group_id: string; merge: boolean };
export type GroupUpdate = { groups: GroupDecision[] };

export type ColumnChoice = ColumnView & { default_selected: boolean };
export type ColumnChoices = {
  group_id: string;
  columns: ColumnChoice[];
  stratify_column: string | null;
};
export type ColumnSelectionUpdate = { selected: string[] };

export type ProjectionMethod = "pca" | "umap";
export type RunOptions = {
  target?: number;
  seed?: number;
  projection_method?: ProjectionMethod;
  projection_dimensions?: 2 | 3;
};
export type RunAccepted = { job_id: string; state: "queued" };
export type RunState = "idle" | "queued" | "running" | "done" | "failed";
export type RunStatus = {
  job_id: string;
  state: RunState;
  progress: number;
  stage: string;
  error: string | null;
};

export type ScoreSummary = {
  total: number;
  distribution: number;
  correlation: number;
  structure: number;
};
export type ScorePoint = {
  size: number;
  score: number;
  distribution: number;
  correlation: number;
  structure: number;
};
export type MethodScore = ScorePoint & { method: string };
export type ProjectionData = {
  method: string;
  dimensions: 2 | 3;
  original: number[][];
  reduced: number[][];
  original_indices: number[];
};
export type GroupResult = {
  name: string;
  files: string[];
  original_rows: number;
  prepared_rows: number;
  reduced_rows: number;
  reduction_method: string;
  score: ScoreSummary;
  size_curve: ScorePoint[];
  method_scores: MethodScore[];
  projection: ProjectionData;
  detail: Record<string, unknown>;
};
export type SkippedGroup = { name: string; files: string[]; reason: string };
export type PipelineResults = {
  folder: string;
  target: number;
  groups: GroupResult[];
  skipped: SkippedGroup[];
};

export type DensityGrid = {
  x_edges: number[];
  y_edges: number[];
  counts: number[][];
};
export type VisualizationMode = "sample" | "density";
export type VisualizationOptions = {
  group: string;
  mode?: VisualizationMode;
  max_points?: number;
  bins?: number;
  seed?: number;
  projection_method?: ProjectionMethod;
  projection_dimensions?: 2 | 3;
};
export type ColumnGraphOptions = {
  group: string;
  column?: string;
};
export type HistogramOptions = ColumnGraphOptions & {
  bins?: number;
};
export type HistogramData = {
  group: string;
  column: string;
  columns: string[];
  edges: number[];
  original_ratios: number[];
  reduced_ratios: number[];
  original_rows: number;
  reduced_rows: number;
  weighted: boolean;
  dropped_original: number;
  dropped_reduced: number;
};
export type BoxSummary = {
  minimum: number;
  q1: number;
  median: number;
  q3: number;
  maximum: number;
  low_whisker: number;
  high_whisker: number;
  outliers: number[];
  outlier_count: number;
  rows: number;
};
export type BoxplotData = {
  group: string;
  column: string;
  columns: string[];
  original: BoxSummary;
  reduced: BoxSummary;
  weighted: boolean;
  dropped_original: number;
  dropped_reduced: number;
};
export type CategoryRatioData = {
  group: string;
  column: string;
  columns: string[];
  categories: string[];
  original_ratios: number[];
  reduced_ratios: number[];
  original_rows: number;
  reduced_rows: number;
  weighted: boolean;
  dropped_original: number;
  dropped_reduced: number;
};
export type VisualizationData = {
  group: string;
  mode: VisualizationMode;
  dimensions: number;
  original_rows: number;
  original_projected: number;
  reduced_rows: number;
  original_points: number[][];
  original_indices: number[];
  original_density: DensityGrid | null;
  reduced_points: number[][];
  projection_method: ProjectionMethod;
};
