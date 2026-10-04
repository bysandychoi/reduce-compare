export function clusterColor(cluster: number) {
  const hue = ((cluster * 137.508) % 360 + 360) % 360;
  return "hsl(" + hue.toFixed(1) + " 55% 42%)";
}
