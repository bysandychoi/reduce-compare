import type {
  ApiOptions,
  ColumnChoices,
  ColumnSelectionUpdate,
  GroupUpdate,
  GroupsView,
  Health,
  JobCreated,
  PipelineResults,
  RunAccepted,
  RunOptions,
  RunStatus,
  UploadItem,
  VisualizationData,
  VisualizationOptions,
} from "./types";

export type * from "./types";

const API_BASE = "/api";

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

function detailMessage(payload: unknown, fallback: string) {
  if (typeof payload !== "object" || payload === null || !("detail" in payload)) return fallback;
  const detail = (payload as { detail: unknown }).detail;
  if (typeof detail === "string") return detail;
  try {
    return JSON.stringify(detail);
  } catch {
    return fallback;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, init);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, "서버에 연결할 수 없습니다", error);
  }

  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    const fallback = response.ok ? "서버 응답 형식이 올바르지 않습니다" : response.statusText;
    throw new ApiError(response.status, fallback || `HTTP ${response.status}`);
  }
  if (!response.ok) {
    const fallback = response.statusText || `HTTP ${response.status}`;
    throw new ApiError(response.status, detailMessage(payload, fallback), payload);
  }
  return payload as T;
}

function jsonRequest<T>(path: string, method: "POST" | "PUT", body: unknown, options: ApiOptions) {
  return request<T>(path, {
    method,
    signal: options.signal,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

function segment(value: string) {
  return encodeURIComponent(value);
}

export function getHealth(options: ApiOptions = {}) {
  return request<Health>("/health", { signal: options.signal });
}

export function createJob(files: UploadItem[], options: ApiOptions = {}) {
  const form = new FormData();
  files.forEach(({ file, path }) => form.append("files", file, path));
  return request<JobCreated>("/jobs", { method: "POST", body: form, signal: options.signal });
}

export function getGroups(jobId: string, options: ApiOptions = {}) {
  return request<GroupsView>(`/jobs/${segment(jobId)}/groups`, { signal: options.signal });
}

export function updateGroups(jobId: string, update: GroupUpdate, options: ApiOptions = {}) {
  return jsonRequest<GroupsView>(`/jobs/${segment(jobId)}/groups`, "PUT", update, options);
}

export function getColumns(jobId: string, groupId: string, options: ApiOptions = {}) {
  return request<ColumnChoices>(
    `/jobs/${segment(jobId)}/groups/${segment(groupId)}/columns`,
    { signal: options.signal },
  );
}

export function updateColumns(
  jobId: string,
  groupId: string,
  update: ColumnSelectionUpdate,
  options: ApiOptions = {},
) {
  const path = `/jobs/${segment(jobId)}/groups/${segment(groupId)}/columns`;
  return jsonRequest<ColumnChoices>(path, "PUT", update, options);
}

export function startRun(jobId: string, run: RunOptions = {}, options: ApiOptions = {}) {
  return jsonRequest<RunAccepted>(`/jobs/${segment(jobId)}/run`, "POST", run, options);
}

export function getRunStatus(jobId: string, options: ApiOptions = {}) {
  return request<RunStatus>(`/jobs/${segment(jobId)}/status`, { signal: options.signal });
}

export function getResult(jobId: string, options: ApiOptions = {}) {
  return request<PipelineResults>(`/jobs/${segment(jobId)}/result`, { signal: options.signal });
}

export function getVisualization(jobId: string, view: VisualizationOptions, options: ApiOptions = {}) {
  const query = new URLSearchParams({ group: view.group });
  if (view.mode !== undefined) query.set("mode", view.mode);
  if (view.max_points !== undefined) query.set("max_points", String(view.max_points));
  if (view.bins !== undefined) query.set("bins", String(view.bins));
  if (view.seed !== undefined) query.set("seed", String(view.seed));
  return request<VisualizationData>(
    `/jobs/${segment(jobId)}/visualization?${query.toString()}`,
    { signal: options.signal },
  );
}
