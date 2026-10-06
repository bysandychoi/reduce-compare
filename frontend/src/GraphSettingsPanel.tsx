import { useId } from "react";

import { settingsForGraph, type GraphKind, type GraphSettingDefinition, type GraphSettings, type GraphSettingValue } from "./graphSettings";

type Props = {
  graph: GraphKind;
  settings: GraphSettings;
  onChange: (key: string, value: GraphSettingValue) => void;
  onReset: () => void;
};

function SettingControl({ definition, id, value, onChange }: {
  definition: GraphSettingDefinition;
  id: string;
  value: GraphSettingValue;
  onChange: Props["onChange"];
}) {
  const descriptionId = `${id}-description`;
  if (definition.type === "boolean") return <label className="graph-setting graph-setting--toggle" htmlFor={id}>
    <span><strong>{definition.label}</strong><small id={descriptionId}>{definition.description}</small></span>
    <input id={id} type="checkbox" checked={Boolean(value)} aria-describedby={descriptionId}
      onChange={(event) => onChange(definition.key, event.target.checked)} />
  </label>;

  return <label className="graph-setting" htmlFor={id}>
    <span><strong>{definition.label}</strong><small id={descriptionId}>{definition.description}</small></span>
    {definition.type === "range" && <span className="graph-setting__range">
      <input id={id} type="range" min={definition.min} max={definition.max} step={definition.step}
        value={Number(value)} aria-describedby={descriptionId}
        onChange={(event) => {
          const next = event.target.valueAsNumber;
          if (Number.isFinite(next)) onChange(definition.key, next);
        }} />
      <output htmlFor={id}>{Number(value).toLocaleString()}</output>
    </span>}
    {definition.type === "color" && <span className="graph-setting__color">
      <input id={id} type="color" value={String(value)} aria-describedby={descriptionId}
        onChange={(event) => onChange(definition.key, event.target.value)} />
      <code>{String(value).toUpperCase()}</code>
    </span>}
    {definition.type === "select" && <select id={id} value={String(value)} aria-describedby={descriptionId}
      onChange={(event) => onChange(definition.key, event.target.value)}>
      {definition.options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
    </select>}
  </label>;
}

export default function GraphSettingsPanel({ graph, settings, onChange, onReset }: Props) {
  const prefix = useId();
  const definitions = settingsForGraph(graph);
  return <details className="graph-settings" open>
    <summary><span>그래프 디자인</span><small>표시만 바꾸며 축소 결과는 다시 계산하지 않습니다.</small></summary>
    <button type="button" className="graph-settings__reset" onClick={onReset}>기본값 복원</button>
    <div className="graph-settings__grid">
      {definitions.map((definition) => <SettingControl key={definition.key}
        definition={definition} id={`${prefix}-${definition.key}`}
        value={settings[definition.key]} onChange={onChange} />)}
    </div>
  </details>;
}
