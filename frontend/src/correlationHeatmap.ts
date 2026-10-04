export type CorrelationHeatmapData = {
  columns: string[];
  method: string;
  original: number[][];
  reduced: number[][];
  difference: number[][];
  undefinedOriginal: boolean[][];
  undefinedReduced: boolean[][];
  undefinedDifference: boolean[][];
  differenceLimit: number;
};

type ParseResult = { data: CorrelationHeatmapData; error?: never } | { data?: never; error: string };

function record(value: unknown): Record<string, unknown> | undefined {
  return typeof value === "object" && value !== null ? value as Record<string, unknown> : undefined;
}

function numberMatrix(value: unknown, size: number) {
  if (!Array.isArray(value) || value.length !== size) return undefined;
  const rows = value.map((row) => Array.isArray(row) && row.length === size
    && row.every((cell) => typeof cell === "number" && Number.isFinite(cell) && Math.abs(cell) <= 1)
    ? row as number[] : undefined);
  return rows.every(Boolean) ? rows as number[][] : undefined;
}

function booleanMatrix(value: unknown, size: number) {
  if (!Array.isArray(value) || value.length !== size) return undefined;
  const rows = value.map((row) => Array.isArray(row) && row.length === size
    && row.every((cell) => typeof cell === "boolean") ? row as boolean[] : undefined);
  return rows.every(Boolean) ? rows as boolean[][] : undefined;
}

export function parseCorrelationHeatmap(detail: Record<string, unknown>): ParseResult {
  const source = record(detail.correlation);
  if (!source) return { error: "상관행렬 결과가 없습니다." };
  const columns = Array.isArray(source.columns) && source.columns.every((item) => typeof item === "string")
    ? source.columns as string[] : undefined;
  if (!columns || new Set(columns).size !== columns.length) {
    return { error: "상관행렬 컬럼 정보가 올바르지 않습니다." };
  }
  const size = columns.length;
  const original = numberMatrix(source.matrix_original, size);
  const reduced = numberMatrix(source.matrix_reduced, size);
  const undefinedOriginal = booleanMatrix(source.undefined_original, size);
  const undefinedReduced = booleanMatrix(source.undefined_reduced, size);
  if (!original || !reduced || !undefinedOriginal || !undefinedReduced) {
    return { error: "상관행렬 또는 측정 불가 정보가 올바르지 않습니다." };
  }
  const undefinedDifference = original.map((row, i) => row.map(
    (_, j) => undefinedOriginal[i][j] || undefinedReduced[i][j],
  ));
  const difference = reduced.map((row, i) => row.map((value, j) => value - original[i][j]));
  const definedDifferences = difference.flatMap((row, i) => row.filter(
    (_, j) => !undefinedDifference[i][j],
  ));
  const differenceLimit = Math.max(0, ...definedDifferences.map((value) => Math.abs(value)));
  return { data: {
    columns, method: typeof source.method === "string" ? source.method : "pearson",
    original, reduced, difference, undefinedOriginal, undefinedReduced,
    undefinedDifference, differenceLimit,
  } };
}

function mix(start: number[], end: number[], amount: number) {
  return start.map((value, index) => Math.round(value + (end[index] - value) * amount));
}

export function correlationColor(value: number, limit: number) {
  const ratio = Math.min(1, Math.abs(value) / Math.max(limit, 1e-12));
  const rgb = value < 0 ? mix([247, 249, 250], [42, 112, 160], ratio)
    : mix([247, 249, 250], [190, 55, 55], ratio);
  return `rgb(${rgb.join(",")})`;
}
