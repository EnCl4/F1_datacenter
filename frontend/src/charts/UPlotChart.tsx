import { useEffect, useRef, useState } from "react";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";
import type { ChartOptions } from "./sync";

interface Props {
  /** Must be memoised by the caller: a new object recreates the chart. */
  options: ChartOptions;
  data: uPlot.AlignedData;
  /** Height of the plot area in px (uPlot adds the legend below it). */
  height: number;
  className?: string;
}

/**
 * Thin React wrapper around uPlot.
 *
 * - The instance is created in an effect and destroyed on unmount.
 * - It is recreated when `options` or `data` change identity.
 * - Resizes go through setSize() instead, so a window resize keeps the zoom.
 */
export function UPlotChart({ options, data, height, className }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const plot = useRef<uPlot | null>(null);
  const [width, setWidth] = useState(0);

  // Track the container width.
  useEffect(() => {
    const el = host.current;
    if (!el) return;
    setWidth(Math.floor(el.clientWidth));
    const observer = new ResizeObserver((entries) => {
      const w = Math.floor(entries[0].contentRect.width);
      setWidth((prev) => (prev === w ? prev : w));
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Width is read through a ref so that resizing does not rebuild the chart; the
  // chart is only built once a real width is known (`ready`).
  const widthRef = useRef(width);
  widthRef.current = width;
  const ready = width > 0;

  useEffect(() => {
    const el = host.current;
    if (!el || !ready) return;
    const u = new uPlot({ ...options, width: widthRef.current, height }, data, el);
    plot.current = u;
    return () => {
      u.destroy();
      plot.current = null;
    };
  }, [options, data, height, ready]);

  useEffect(() => {
    if (ready) plot.current?.setSize({ width, height });
  }, [width, height, ready]);

  return <div ref={host} className={className ?? "uplot-host"} />;
}
