const MIN_SCALE = .65;
const MAX_SCALE = 1.8;

export function pointSizes(weights: number[] | undefined, count: number, baseSize: number, weighted: boolean) {
  const fallback = () => Array.from({ length: count }, () => baseSize);
  if (!weighted || !weights || weights.length !== count || count === 0
      || weights.some((weight) => !Number.isFinite(weight) || weight <= 0)) return fallback();
  const sorted = [...weights].sort((left, right) => left - right);
  const middle = Math.floor(sorted.length / 2);
  const median = sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
  if (!Number.isFinite(median) || median <= 0) return fallback();
  return weights.map((weight) => baseSize * Math.max(MIN_SCALE, Math.min(MAX_SCALE, Math.sqrt(weight / median))));
}
