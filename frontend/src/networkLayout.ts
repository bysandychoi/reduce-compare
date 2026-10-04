import type { NetworkGraph } from "./api/client";

export type NetworkLayout = "circular" | "force";
export type NetworkPoint = { x: number; y: number };
const CENTER = 210;
const RADIUS = 142;

export function circularPositions(graph: NetworkGraph) {
  return new Map(graph.nodes.map((node, index) => {
    const angle = -Math.PI / 2 + 2 * Math.PI * index / Math.max(1, graph.nodes.length);
    return [node.id, { x: CENTER + RADIUS * Math.cos(angle), y: CENTER + RADIUS * Math.sin(angle) }];
  }));
}

export function forcePositions(graph: NetworkGraph) {
  const points = circularPositions(graph);
  const nodes = graph.nodes.map((node) => node.id);
  for (let iteration = 0; iteration < 90; iteration += 1) {
    const forces = new Map(nodes.map((id) => [id, { x: 0, y: 0 }]));
    for (let a = 0; a < nodes.length; a += 1) for (let b = a + 1; b < nodes.length; b += 1) {
      const first = points.get(nodes[a]) as NetworkPoint;
      const second = points.get(nodes[b]) as NetworkPoint;
      let dx = first.x - second.x, dy = first.y - second.y;
      if (dx === 0 && dy === 0) { dx = (a + 1) * .01; dy = (b + 1) * .01; }
      const distance = Math.max(12, Math.hypot(dx, dy));
      const strength = 1500 / (distance * distance);
      const fx = strength * dx / distance, fy = strength * dy / distance;
      forces.get(nodes[a])!.x += fx; forces.get(nodes[a])!.y += fy;
      forces.get(nodes[b])!.x -= fx; forces.get(nodes[b])!.y -= fy;
    }
    for (const edge of graph.edges) {
      const from = points.get(edge.source), to = points.get(edge.target);
      if (!from || !to) continue;
      const dx = to.x - from.x, dy = to.y - from.y;
      const distance = Math.max(1, Math.hypot(dx, dy));
      const pull = (distance - 105) * .008 * (.5 + edge.weight);
      forces.get(edge.source)!.x += pull * dx / distance; forces.get(edge.source)!.y += pull * dy / distance;
      forces.get(edge.target)!.x -= pull * dx / distance; forces.get(edge.target)!.y -= pull * dy / distance;
    }
    const cooling = 1 - iteration / 110;
    for (const id of nodes) {
      const point = points.get(id)!, force = forces.get(id)!;
      point.x = Math.max(38, Math.min(382, point.x + (force.x + (CENTER - point.x) * .002) * cooling));
      point.y = Math.max(38, Math.min(382, point.y + (force.y + (CENTER - point.y) * .002) * cooling));
    }
  }
  return points;
}

export function networkPositions(graph: NetworkGraph, layout: NetworkLayout) {
  return layout === "force" ? forcePositions(graph) : circularPositions(graph);
}
