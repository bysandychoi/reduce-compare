import type { GroupResult } from "./api/client";
import { methodLabel } from "./SummaryCards";

export default function MethodScoreBars({ group }: { group: GroupResult }) {
  const methods = [...group.method_scores].sort((a, b) => b.score - a.score);
  return <section className="method-section" aria-labelledby="method-title">
    <div className="method-heading">
      <div><span>추천 근거</span><h4 id="method-title">방식별 종합 점수</h4></div>
      <p>동일한 {group.reduced_rows.toLocaleString()}행에서 비교했습니다.</p>
    </div>
    {methods.length ? <ol className="method-bars">
      {methods.map((item) => {
        const selected = item.method === group.reduction_method;
        return <li key={item.method} className={selected ? "method-bar method-bar--selected" : "method-bar"}>
          <div className="method-bar__label"><strong>{methodLabel(item.method)}</strong>{selected && <span>추천</span>}</div>
          <div className="method-bar__track" role="meter" aria-label={`${methodLabel(item.method)} 종합 점수`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={item.score}>
            <i style={{ width: `${Math.min(100, Math.max(0, item.score))}%` }} />
          </div>
          <b>{item.score.toFixed(1)}</b>
        </li>;
      })}
    </ol> : <p className="curve-empty">비교 가능한 축소 방식이 없습니다.</p>}
  </section>;
}
