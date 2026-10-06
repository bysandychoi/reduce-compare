import { useEffect } from "react";

export default function useAxisCompatibility(
  columns: string[], xAxis: string, yAxis: string, zAxis: string,
  setX: (value: string) => void, setY: (value: string) => void, setZ: (value: string) => void,
) {
  const columnKey = columns.join("\0");
  useEffect(() => {
    const available = new Set(columnKey.split("\0"));
    if (xAxis.startsWith("column:") && !available.has(xAxis.slice(7))) setX("projection:0");
    if (yAxis.startsWith("column:") && !available.has(yAxis.slice(7))) setY("projection:1");
    if (zAxis.startsWith("column:") && !available.has(zAxis.slice(7))) setZ("projection:2");
  }, [columnKey, xAxis, yAxis, zAxis, setX, setY, setZ]);
}
