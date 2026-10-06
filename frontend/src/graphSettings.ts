export type GraphKind = "scatter-2d" | "scatter-3d" | "histogram" | "boxplot"
  | "category-ratio" | "correlation-heatmap" | "network";

type BaseSetting<T extends string, V> = {
  type: T;
  key: string;
  label: string;
  description: string;
  defaultValue: V;
  graphs: readonly GraphKind[];
};

export type RangeSetting = BaseSetting<"range", number> & {
  min: number;
  max: number;
  step: number;
};
export type ColorSetting = BaseSetting<"color", string>;
export type SelectSetting = BaseSetting<"select", string> & {
  options: readonly { value: string; label: string }[];
};
export type BooleanSetting = BaseSetting<"boolean", boolean>;
export type GraphSettingDefinition = RangeSetting | ColorSetting | SelectSetting | BooleanSetting;
export type GraphSettingValue = string | number | boolean;
export type GraphSettings = Record<string, GraphSettingValue>;

const ALL_GRAPHS: readonly GraphKind[] = [
  "scatter-2d", "scatter-3d", "histogram", "boxplot", "category-ratio",
  "correlation-heatmap", "network",
];

export const GRAPH_SETTING_SCHEMA: readonly GraphSettingDefinition[] = [
  {
    type: "select", key: "palette", label: "색상 팔레트",
    description: "원본과 축소본을 구별할 색상 조합을 선택합니다.", defaultValue: "default",
    options: [
      { value: "default", label: "기본" },
      { value: "colorblind", label: "색각친화" },
      { value: "high-contrast", label: "고대비" },
      { value: "custom", label: "사용자 지정" },
    ], graphs: ["scatter-2d", "scatter-3d", "histogram", "boxplot", "category-ratio"],
  },
  {
    type: "color", key: "originalColor", label: "원본 색상",
    description: "원본 계열의 기본 색상입니다.", defaultValue: "#7c8794",
    graphs: ["scatter-2d", "scatter-3d", "histogram", "boxplot", "category-ratio"],
  },
  {
    type: "color", key: "reducedColor", label: "축소본 색상",
    description: "축소본 계열의 기본 색상입니다.", defaultValue: "#176b9b",
    graphs: ["scatter-2d", "scatter-3d", "histogram", "boxplot", "category-ratio"],
  },
  {
    type: "range", key: "pointSize", label: "점 크기",
    description: "산점도 점의 지름을 조절합니다.", defaultValue: 4,
    min: 1, max: 12, step: .5, graphs: ["scatter-2d", "scatter-3d"],
  },
  {
    type: "range", key: "opacity", label: "투명도",
    description: "그래프 요소의 불투명도를 조절합니다.", defaultValue: .65,
    min: .1, max: 1, step: .05, graphs: ALL_GRAPHS,
  },
  {
    type: "select", key: "networkLayout", label: "네트워크 배치",
    description: "상관 네트워크의 노드 배치 방식을 선택합니다.", defaultValue: "circular",
    options: [{ value: "circular", label: "원형" }, { value: "force", label: "힘 기반" }],
    graphs: ["network"],
  },
  {
    type: "range", key: "correlationThreshold", label: "엣지 임계값",
    description: "이 절댓값 이상의 상관관계만 엣지로 표시합니다.", defaultValue: .5,
    min: 0, max: 1, step: .05, graphs: ["network"],
  },
  {
    type: "boolean", key: "showLegend", label: "범례 표시",
    description: "원본·축소본과 그래프 기호를 설명하는 범례를 표시합니다.",
    defaultValue: true, graphs: ALL_GRAPHS,
  },
];

function validRange(definition: RangeSetting, value: unknown) {
  if (typeof value !== "number" || !Number.isFinite(value)
      || value < definition.min || value > definition.max) return false;
  const steps = (value - definition.min) / definition.step;
  return Math.abs(steps - Math.round(steps)) < 1e-8;
}

function validValue(definition: GraphSettingDefinition, value: unknown) {
  if (definition.type === "boolean") return typeof value === "boolean";
  if (definition.type === "color") return typeof value === "string" && /^#[0-9a-f]{6}$/i.test(value);
  if (definition.type === "select") return typeof value === "string"
    && definition.options.some((option) => option.value === value);
  return validRange(definition, value);
}

export function validateSettingSchema(schema: readonly GraphSettingDefinition[]) {
  const keys = new Set<string>();
  for (const definition of schema) {
    if (!definition.key.trim() || keys.has(definition.key)) throw new Error(`중복되거나 빈 설정 key: ${definition.key}`);
    keys.add(definition.key);
    if (!definition.label.trim() || !definition.description.trim()) {
      throw new Error(`${definition.key}: label과 description은 비어 있을 수 없습니다`);
    }
    if (!definition.graphs.length || new Set(definition.graphs).size !== definition.graphs.length) {
      throw new Error(`${definition.key}: 적용 graph가 없거나 중복됐습니다`);
    }
    if (definition.type === "range"
        && (!Number.isFinite(definition.min) || !Number.isFinite(definition.max)
          || !Number.isFinite(definition.step) || definition.min > definition.max || definition.step <= 0)) {
      throw new Error(`${definition.key}: range 범위가 올바르지 않습니다`);
    }
    if (definition.type === "select") {
      const values = definition.options.map((option) => option.value);
      if (!values.length || new Set(values).size !== values.length
          || definition.options.some((option) => !option.value.trim() || !option.label.trim())) {
        throw new Error(`${definition.key}: select option이 없거나 중복됐습니다`);
      }
    }
    if (!validValue(definition, definition.defaultValue)) {
      throw new Error(`${definition.key}: 기본값이 정의와 맞지 않습니다`);
    }
  }
  return schema;
}

validateSettingSchema(GRAPH_SETTING_SCHEMA);

export function settingsForGraph(graph: GraphKind) {
  return GRAPH_SETTING_SCHEMA.filter((definition) => definition.graphs.includes(graph));
}

export function defaultGraphSettings(): GraphSettings {
  return Object.fromEntries(GRAPH_SETTING_SCHEMA.map(
    (definition) => [definition.key, definition.defaultValue],
  ));
}

export function normalizeGraphSettings(value: unknown): GraphSettings {
  const source = typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown> : {};
  return Object.fromEntries(GRAPH_SETTING_SCHEMA.map((definition) => [
    definition.key,
    validValue(definition, source[definition.key])
      ? source[definition.key] as GraphSettingValue : definition.defaultValue,
  ]));
}
