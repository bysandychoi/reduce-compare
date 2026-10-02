import { useMemo, useState } from "react";

import type { GroupResult } from "./api/client";

type MetricRow = { category: string; item: string; score: number };
type SortKey = keyof MetricRow;

function columnRows(detail: Record<string, unknown>): MetricRow[] {
  const columns = detail.columns;
  if (!Array.isArray(columns)) return [];
  return columns.flatMap((entry) => {
    if (typeof entry !== "object" || entry === null) return [];
    const { name, score } = entry as { name?: unknown; score?: unknown };
    return typeof name === "string" && typeof score === "number"
      ? [{ category: "분포", item: name, score }]
      : [];
  });
}

export default function MetricTable({ group }: { group: GroupResult }) {
  const [sort, setSort] = useState<{ key: SortKey; direction: "asc" | "desc" }>({
    key: "score", direction: "desc",
  });
  const rows = useMemo(() => [
    { category: "분포", item: "전체", score: group.score.distribution },
    { category: "상관", item: "전체", score: group.score.correlation },
    { category: "구조", item: "전체", score: group.score.structure },
    ...columnRows(group.detail),
  ].sort((a, b) => {
    const result = typeof a[sort.key] === "number"
      ? (a[sort.key] as number) - (b[sort.key] as number)
      : String(a[sort.key]).localeCompare(String(b[sort.key]), "ko");
    return sort.direction === "asc" ? result : -result;
  }), [group, sort]);

  function changeSort(key: SortKey) {
    setSort((current) => ({
      key,
      direction: current.key === key && current.direction === "asc" ? "desc" : "asc",
    }));
  }

  const columns: { key: SortKey; label: string }[] = [
    { key: "category", label: "지표" }, { key: "item", label: "항목" }, { key: "score", label: "점수" },
  ];
  return <section className="metric-section" aria-labelledby="metric-title">
    <div className="metric-section__heading">
      <div><span>세부 지표</span><h4 id="metric-title">항목별 보존 점수</h4></div>
      <p>100점에 가까울수록 원본과 유사합니다.</p>
    </div>
    <div className="metric-table-wrap">
      <table className="metric-table">
        <thead><tr>{columns.map((column) => <th key={column.key} scope="col" aria-sort={sort.key === column.key ? (sort.direction === "asc" ? "ascending" : "descending") : "none"}>
          <button type="button" onClick={() => changeSort(column.key)}>{column.label}<span aria-hidden="true">{sort.key === column.key ? (sort.direction === "asc" ? " ↑" : " ↓") : " ↕"}</span></button>
        </th>)}</tr></thead>
        <tbody>{rows.map((row, index) => <tr key={`${row.category}-${row.item}-${index}`}>
          <td><span className={`metric-badge metric-badge--${row.category}`}>{row.category}</span></td>
          <th scope="row">{row.item}</th>
          <td><strong>{row.score.toFixed(1)}</strong><span> / 100</span></td>
        </tr>)}</tbody>
      </table>
    </div>
  </section>;
}
