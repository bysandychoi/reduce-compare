import type { GroupResult } from "./api/client";

export const METHOD_LABELS: Record<string, string> = {
  cluster_actual: "군집 기반 · 실제 행",
  cluster_mean: "군집 기반 · 평균 행",
  stratified: "층화 샘플링",
  random: "랜덤 샘플링",
};

export function methodLabel(method: string) {
  return METHOD_LABELS[method] ?? method;
}

function reductionRatio(group: GroupResult) {
  if (group.original_rows <= 0) return "0.00%";
  return `${(group.reduced_rows / group.original_rows * 100).toFixed(2)}%`;
}

export default function SummaryCards({ group }: { group: GroupResult }) {
  const cards = [
    { label: "원본 행 수", value: `${group.original_rows.toLocaleString()}행` },
    { label: "축소 행 수", value: `${group.reduced_rows.toLocaleString()}행` },
    { label: "축소 비율", value: reductionRatio(group) },
    { label: "추천 방식", value: methodLabel(group.reduction_method) },
    { label: "종합 점수", value: `${group.score.total.toFixed(1)}점`, accent: true },
  ];
  return <dl className="summary-cards">
    {cards.map((card) => <div key={card.label} className={card.accent ? "summary-card summary-card--accent" : "summary-card"}>
      <dt>{card.label}</dt><dd>{card.value}</dd>
    </div>)}
  </dl>;
}
