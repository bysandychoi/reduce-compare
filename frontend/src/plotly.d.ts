declare module "plotly.js-dist-min" {
  export type PlotElement = HTMLDivElement & {
    on(event: string, callback: (update: Record<string, unknown>) => void): void;
    removeAllListeners(event: string): void;
  };
  const Plotly: {
    newPlot(element: PlotElement, data: unknown[], layout: Record<string, unknown>, config: Record<string, unknown>): Promise<PlotElement>;
    relayout(element: PlotElement, update: Record<string, unknown>): Promise<void>;
    purge(element: PlotElement): void;
  };
  export default Plotly;
}
