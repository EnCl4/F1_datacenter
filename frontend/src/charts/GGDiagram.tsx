import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { LapTrace } from "../api";
import { chartColors } from "./theme";
import { nearestIndex } from "./trace";

const MARGIN = 34;
const MAX_SIZE = 460;

interface Props {
  lap: LapTrace;
  reference: LapTrace;
  /** Distance under the pointer on the trace charts; null when the pointer is elsewhere. */
  cursorDistance: number | null;
}

function maxAbs(trace: LapTrace): number {
  let m = 0;
  const { g_lat, g_lon } = trace.channels;
  for (let i = 0; i < g_lat.length; i++) {
    const a = g_lat[i];
    const b = g_lon[i];
    if (a != null && Math.abs(a) > m) m = Math.abs(a);
    if (b != null && Math.abs(b) > m) m = Math.abs(b);
  }
  return m;
}

/**
 * G-G diagram (US4): every sample of the lap(s) plotted as cornering force (x) against
 * braking/acceleration force (y). Both axes share one scale and the plot is square, so
 * the 1 g to 4 g reference circles stay circles. The sample at the traces' cursor is
 * ringed on each lap.
 *
 * Thousands of points are painted once into an offscreen layer; the cursor ring is
 * composited on top per move, the same way the track map does it.
 */
function GGDiagramImpl({ lap, reference, cursorDistance }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const base = useRef<HTMLCanvasElement | null>(null);
  const [hostWidth, setHostWidth] = useState(0);

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    setHostWidth(Math.floor(el.clientWidth));
    const observer = new ResizeObserver((entries) => {
      const w = Math.floor(entries[0].contentRect.width);
      setHostWidth((prev) => (prev === w ? prev : w));
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const size = Math.max(0, Math.min(hostWidth, MAX_SIZE));

  // Limit of both axes in g: the data's extent rounded up to a whole g, so the circle
  // labels land on gridlines. Symmetric on purpose (braking is ~2x the acceleration).
  const limit = useMemo(
    () => Math.max(1, Math.ceil(Math.max(maxAbs(lap), maxAbs(reference)))),
    [lap, reference],
  );
  const hasData = useMemo(
    () => lap.channels.g_lat.some((v) => v != null) || reference.channels.g_lat.some((v) => v != null),
    [lap, reference],
  );

  const scale = size > 0 ? (size - 2 * MARGIN) / (2 * limit) : 1;
  const toX = useCallback((g: number) => size / 2 + g * scale, [size, scale]);
  const toY = useCallback((g: number) => size / 2 - g * scale, [size, scale]);

  const paint = useCallback(
    (distance: number | null) => {
      const target = canvas.current;
      const layer = base.current;
      if (!target || !layer) return;
      const ctx = target.getContext("2d");
      if (!ctx) return;
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, target.width, target.height);
      ctx.drawImage(layer, 0, 0);
      if (distance === null) return;
      const colors = chartColors();
      const dpr = target.width / Math.max(1, size);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      for (const [trace, color] of [
        [reference, colors.reference],
        [lap, colors.accent],
      ] as const) {
        const d = trace.channels.distance_m;
        if (!d.length) continue;
        const i = nearestIndex(d, distance);
        const gx = trace.channels.g_lat[i];
        const gy = trace.channels.g_lon[i];
        if (gx == null || gy == null) continue;
        ctx.beginPath();
        ctx.arc(toX(gx), toY(gy), 6.5, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();
        ctx.lineWidth = 2.5;
        ctx.strokeStyle = colors.fg;
        ctx.stroke();
      }
    },
    [lap, reference, size, toX, toY],
  );

  // Rebuild the static layer when the laps or the size change.
  useEffect(() => {
    const target = canvas.current;
    if (!target || size <= 0) return;
    const dpr = window.devicePixelRatio || 1;
    target.width = Math.floor(size * dpr);
    target.height = Math.floor(size * dpr);
    const layer = document.createElement("canvas");
    layer.width = target.width;
    layer.height = target.height;
    base.current = layer;
    const ctx = layer.getContext("2d");
    if (!ctx) return;
    ctx.scale(dpr, dpr);
    const colors = chartColors();

    // Reference circles at 1 g, 2 g, ... up to the axis limit.
    ctx.lineWidth = 1;
    ctx.font = "11px 'Segoe UI', system-ui, sans-serif";
    ctx.textBaseline = "middle";
    for (let g = 1; g <= limit; g++) {
      ctx.strokeStyle = colors.line;
      ctx.globalAlpha = 0.9;
      ctx.beginPath();
      ctx.arc(size / 2, size / 2, g * scale, 0, Math.PI * 2);
      ctx.stroke();
      ctx.globalAlpha = 1;
      ctx.fillStyle = colors.dim;
      ctx.textAlign = "left";
      ctx.fillText(`${g} g`, toX(g * Math.SQRT1_2) + 3, toY(g * Math.SQRT1_2) - 6);
    }

    // Axes through the origin.
    ctx.strokeStyle = colors.dim;
    ctx.globalAlpha = 0.6;
    ctx.beginPath();
    ctx.moveTo(MARGIN, size / 2);
    ctx.lineTo(size - MARGIN, size / 2);
    ctx.moveTo(size / 2, MARGIN);
    ctx.lineTo(size / 2, size - MARGIN);
    ctx.stroke();
    ctx.globalAlpha = 1;

    ctx.fillStyle = colors.dim;
    ctx.textAlign = "center";
    ctx.textBaseline = "alphabetic";
    ctx.fillText("Lateral g", size / 2, size - 10);
    ctx.textBaseline = "top";
    ctx.textAlign = "left";
    ctx.fillText("↑ accelerating", MARGIN + 4, 8);
    ctx.textBaseline = "alphabetic";
    ctx.fillText("↓ braking", MARGIN + 4, size - 10);

    // Samples: reference first so the compared lap stays visible on top.
    const dots = (trace: LapTrace, color: string) => {
      const { g_lat, g_lon } = trace.channels;
      ctx.fillStyle = color;
      ctx.globalAlpha = 0.55;
      for (let i = 0; i < g_lat.length; i++) {
        const gx = g_lat[i];
        const gy = g_lon[i];
        if (gx == null || gy == null) continue; // gaps stay gaps
        ctx.beginPath();
        ctx.arc(toX(gx), toY(gy), 1.7, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
    };
    dots(reference, colors.reference);
    dots(lap, colors.accent);

    paint(null);
  }, [lap, reference, size, limit, scale, toX, toY, paint]);

  useEffect(() => {
    paint(cursorDistance);
  }, [cursorDistance, paint]);

  // Read-out of the two samples at the cursor.
  const readout = useMemo(() => {
    if (cursorDistance === null) return null;
    const at = (t: LapTrace) => {
      const d = t.channels.distance_m;
      if (!d.length) return null;
      const i = nearestIndex(d, cursorDistance);
      const gx = t.channels.g_lat[i];
      const gy = t.channels.g_lon[i];
      return gx == null || gy == null ? null : { lat: gx, lon: gy };
    };
    return { lap: at(lap), reference: at(reference) };
  }, [cursorDistance, lap, reference]);

  const fmt = (v: { lat: number; lon: number } | null) =>
    v ? `${v.lat.toFixed(2)} lat / ${v.lon.toFixed(2)} lon` : "no data";

  return (
    <div className="gg-diagram">
      <div className="chart-title">G-G diagram</div>
      <div className="chart-caption">
        Cornering force against braking and acceleration. Circles mark 1 g steps.
      </div>
      <div className="gg-legend">
        <span>
          <span className="key" style={{ background: "var(--accent)" }} /> Lap {lap.lap_number}
        </span>
        <span>
          <span className="key" style={{ background: "var(--amber)" }} /> Ref lap {reference.lap_number}
        </span>
      </div>
      <div ref={host} className="gg-canvas-host">
        {hasData ? (
          <canvas ref={canvas} style={{ width: size, height: size }} />
        ) : (
          <div className="chart-caption">No g-force data was recorded for these laps.</div>
        )}
      </div>
      <div className="gg-readout">
        {readout ? (
          <>
            <span>
              Lap {lap.lap_number}: {fmt(readout.lap)}
            </span>
            <span>
              Ref {reference.lap_number}: {fmt(readout.reference)}
            </span>
          </>
        ) : (
          <span className="dim">Move over the traces to highlight a point here.</span>
        )}
      </div>
    </div>
  );
}

export const GGDiagram = memo(GGDiagramImpl);
