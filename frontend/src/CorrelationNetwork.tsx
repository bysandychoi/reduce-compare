import type { NetworkGraph } from "./api/client";

type Point = { x: number; y: number };
const CENTER = 210;
const RADIUS = 142;

function positions(graph: NetworkGraph) {
  return new Map(graph.nodes.map((node, index) => {
    const angle = -Math.PI / 2 + 2 * Math.PI * index / Math.max(1, graph.nodes.length);
    return [node.id, { x: CENTER + RADIUS * Math.cos(angle), y: CENTER + RADIUS * Math.sin(angle) }];
  }));
}

function pair(source: string, target: string) {
  return source < target ? `${source}\0${target}` : `${target}\0${source}`;
}

function short(value: string) {
  return value.length > 12 ? `${value.slice(0, 11)}…` : value;
}

export default function CorrelationNetwork({ graph, other, title }: { graph: NetworkGraph; other: NetworkGraph; title: string }) {
  const points = positions(graph);
  const otherPairs = new Set(other.edges.map((edge) => pair(edge.source, edge.target)));
  return <section className="network-panel"><strong>{title}</strong>
    <svg className="network-graph" viewBox="0 0 420 420" role="img" aria-label={`${title} 상관 네트워크`}>
      {graph.edges.map((edge) => {
        const from = points.get(edge.source) as Point;
        const to = points.get(edge.target) as Point;
        const unique = !otherPairs.has(pair(edge.source, edge.target));
        return <line key={pair(edge.source, edge.target)} x1={from.x} y1={from.y} x2={to.x} y2={to.y}
          className={`network-edge network-edge--${edge.sign}${unique ? " network-edge--unique" : ""}`}
          strokeWidth={1.5 + edge.weight * 5}>
          <title>{edge.source} × {edge.target} · r={edge.correlation.toFixed(3)}{unique ? " · 이쪽에만 있음" : ""}</title>
        </line>;
      })}
      {graph.nodes.map((node) => {
        const point = points.get(node.id) as Point;
        return <g className="network-node" key={node.id} transform={`translate(${point.x} ${point.y})`}>
          <circle r="29"><title>{node.label}</title></circle>
          <text textAnchor="middle" y="4"><title>{node.label}</title>{short(node.label)}</text>
        </g>;
      })}
    </svg>
    <span className="network-count">노드 {graph.nodes.length}개 · 관계 {graph.edges.length}개</span>
  </section>;
}
