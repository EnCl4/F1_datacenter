import { memo, useCallback, useEffect, useRef, useState } from "react";
import type { LapTrace } from "../api";
import { chartColors } from "./theme";

type MapChannel = "speed_kph" | "throttle" | "brake";

const CHANNEL_OPTIONS: { key: MapChannel; label: string; unit: string; scale: number }[] = [
  { key: "speed_kph", label: "Speed", unit: "km/h", scale: 1 },
  { key: "throttle", label: "Throttle", unit: "%", scale: 100 },
  { key: "brake", label: "Brake", unit: "%", scale: 100 },
];

const MAP_HEIGHT = 340;
const PADDING = 24;

/** Blue (low) -> green -> red (high). Hue 230 -> 0 passes through green near the middle. */
function ramp(t: number): string {
  const clamped = Math.min(1, Math.max(0, t));
  return `hsl(${Math.round(230 * (1 - clamped))}, 80%, 55%)`;
}

/** Index of the sample whose distance is closest to `d` (distance_m is ascending). */
function nearestIndex(distances: number[], d: number): number {
  let lo = 0;
  let hi = distances.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (distances[mid] < d) lo = mid + 1;
    else hi = mid;
  }
  if (lo > 0 && Math.abs(distances[lo - 1] - d) <= Math.abs(distances[lo] - d)) return lo - 1;
  return lo;
}

interface Props {
  trace: LapTrace;
  /** Drawn first as a dim full outline, so gaps in `trace` read as "no data" rather than a broken circuit. */
  reference?: LapTrace;
  /** Distance under the pointer on the charts; null when the pointer is elsewhere. */
  cursorDistance: number | null;
}

/**
 * Top-down circuit drawn from the car's own recorded x/z positions (FR-024), coloured
 * by a selectable channel (FR-025) and showing the point under the charts' cursor
 * (FR-026). No external map data is involved.
 *
 * The coloured line is expensive (thousands of segments), so it is painted once into
 * an offscreen canvas and the cursor marker is composited on top per cursor move.
 */
function TrackMapImpl({ trace, reference, cursorDistance }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const base = useRef<HTMLCanvasElement | null>(null);
  // Maps a trace + sample index to canvas CSS px; rebuilt with the base layer.
  const project = useRef<((t: LapTrace, i: number) => [number, number] | null) | null>(null);

  const [channel, setChannel] = useState<MapChannel>("speed_kph");
  const [width, setWidth] = useState(0);
  const [range, setRange] = useState<{ min: number; max: number } | null>(null);

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

  /** Composite the base layer plus the marker onto the visible canvas. */
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
      if (distance === null || !project.current) return;

      // Prefer the compared lap's position; where it has none (a recording gap) use
      // the reference lap's position at the same distance.
      const at = (t: LapTrace) => {
        const d = t.channels.distance_m;
        return d.length ? project.current?.(t, nearestIndex(d, distance)) ?? null : null;
      };
      const pos = at(trace) ?? (reference ? at(reference) : null);
      if (!pos) return;
      const dpr = target.width / Math.max(1, width);
      const colors = chartColors();
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.beginPath();
      ctx.arc(pos[0], pos[1], 7, 0, Math.PI * 2);
      ctx.fillStyle = colors.fg;
      ctx.fill();
      ctx.lineWidth = 3;
      ctx.strokeStyle = colors.panel;
      ctx.stroke();
    },
    [trace, reference, width],
  );

  // Rebuild the base layer when the lap, channel or size changes.
  useEffect(() => {
    const target = canvas.current;
    if (!target || width <= 0) return;
    const dpr = window.devicePixelRatio || 1;
    target.width = Math.floor(width * dpr);
    target.height = Math.floor(MAP_HEIGHT * dpr);

    const layer = document.createElement("canvas");
    layer.width = target.width;
    layer.height = target.height;
    base.current = layer;
    const ctx = layer.getContext("2d");
    if (!ctx) return;
    ctx.scale(dpr, dpr);

    const spec = CHANNEL_OPTIONS.find((c) => c.key === channel) ?? CHANNEL_OPTIONS[0];
    const values = trace.channels[channel];
    const hasXZ = (t: LapTrace) =>
      t.channels.x.some((v) => v != null) && t.channels.z.some((v) => v != null);
    // The outline is the reference lap's full path when it has one; otherwise
    // whichever lap has positions.
    const outline = reference && hasXZ(reference) ? reference : trace;

    // Bounding box over everything that will be drawn, so both laps share one frame.
    let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity;
    for (const t of outline === trace ? [trace] : [outline, trace]) {
      const { x, z } = t.channels;
      for (let i = 0; i < x.length; i++) {
        const xv = x[i], zv = z[i];
        if (xv == null || zv == null) continue;
        if (xv < minX) minX = xv;
        if (xv > maxX) maxX = xv;
        if (zv < minZ) minZ = zv;
        if (zv > maxZ) maxZ = zv;
      }
    }
    if (!Number.isFinite(minX)) {
      project.current = null;
      setRange(null);
      return;
    }

    // One uniform scale for both axes keeps the circuit's true shape.
    const spanX = Math.max(maxX - minX, 1);
    const spanZ = Math.max(maxZ - minZ, 1);
    const scale = Math.min((width - 2 * PADDING) / spanX, (MAP_HEIGHT - 2 * PADDING) / spanZ);
    const offX = (width - spanX * scale) / 2;
    const offY = (MAP_HEIGHT - spanZ * scale) / 2;
    // Screen y grows downward but world z grows "north", so flip z to keep the
    // circuit the right way round rather than mirrored.
    const toScreen = (t: LapTrace, i: number): [number, number] | null => {
      const xv = t.channels.x[i], zv = t.channels.z[i];
      if (xv == null || zv == null) return null;
      return [offX + (xv - minX) * scale, offY + (maxZ - zv) * scale];
    };
    project.current = toScreen;

    // Colour scale: throttle/brake are 0..1; speed spans the lap's own range.
    let lo = 0;
    let hi = 1;
    if (channel === "speed_kph") {
      lo = Infinity;
      hi = -Infinity;
      for (const v of values) {
        if (v == null) continue;
        if (v < lo) lo = v;
        if (v > hi) hi = v;
      }
      if (!Number.isFinite(lo)) { lo = 0; hi = 1; }
    }
    setRange({ min: lo * spec.scale, max: hi * spec.scale });

    ctx.lineCap = "round";
    ctx.lineJoin = "round";

    // 1) Thin dim outline of the whole circuit.
    ctx.lineWidth = 2;
    ctx.strokeStyle = chartColors().line;
    ctx.beginPath();
    let pen = false;
    for (let i = 0; i < outline.channels.x.length; i++) {
      const p = toScreen(outline, i);
      if (!p) { pen = false; continue; }
      if (pen) ctx.lineTo(p[0], p[1]);
      else ctx.moveTo(p[0], p[1]);
      pen = true;
    }
    ctx.stroke();

    // 2) Compared lap's coloured line on top, only where it has data.
    ctx.lineWidth = 4;
    for (let i = 1; i < trace.channels.x.length; i++) {
      const a = toScreen(trace, i - 1);
      const b = toScreen(trace, i);
      const v = values[i];
      if (!a || !b || v == null) continue; // gaps stay gaps: "no data here"
      ctx.strokeStyle = ramp((v - lo) / Math.max(hi - lo, 1e-9));
      ctx.beginPath();
      ctx.moveTo(a[0], a[1]);
      ctx.lineTo(b[0], b[1]);
      ctx.stroke();
    }

    paint(null);
  }, [trace, reference, channel, width, paint]);

  // Marker follows the charts' cursor without rebuilding the base layer.
  useEffect(() => {
    paint(cursorDistance);
  }, [cursorDistance, paint]);

  const spec = CHANNEL_OPTIONS.find((c) => c.key === channel) ?? CHANNEL_OPTIONS[0];

  return (
    <div className="track-map">
      <div className="map-head">
        <div className="chart-title">Track map</div>
        <div className="segmented" role="group" aria-label="Colour the track by">
          {CHANNEL_OPTIONS.map((c) => (
            <button
              key={c.key}
              type="button"
              className={c.key === channel ? "active" : ""}
              onClick={() => setChannel(c.key)}
            >
              {c.label}
            </button>
          ))}
        </div>
      </div>
      <div ref={host} className="map-canvas-host">
        <canvas ref={canvas} style={{ width: "100%", height: MAP_HEIGHT }} />
      </div>
      {range ? (
        <div className="map-legend">
          <span>
            {Math.round(range.min)} {spec.unit}
          </span>
          <span className="ramp" />
          <span>
            {Math.round(range.max)} {spec.unit}
          </span>
        </div>
      ) : (
        <div className="chart-caption">No position data recorded for this lap.</div>
      )}
    </div>
  );
}

export const TrackMap = memo(TrackMapImpl);
