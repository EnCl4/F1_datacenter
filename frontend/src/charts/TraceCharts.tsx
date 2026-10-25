import { memo, useCallback, useMemo, useRef, useState, type ReactNode } from "react";
import uPlot from "uplot";
import { WHEELS, WHEEL_NAMES, type ChannelKey, type LapTrace, type Wheel } from "../api";
import { UPlotChart } from "./UPlotChart";
import { axisStyle, chartColors, Y_AXIS_SIZE } from "./theme";
import { cursorDistanceHook, sectorLinesHook, withSync, type ChartOptions } from "./sync";
import { offTrackRuns, type DistanceRun } from "./trace";

interface LineSpec {
  channel: ChannelKey;
  /** Names the line when a chart carries more than one (e.g. "lateral"). */
  name?: string;
  /** Multiplier from the raw value to the displayed one (0..1 -> %). */
  scale?: number;
}

interface ChartSpec {
  id: string;
  title: string;
  unit: string;
  decimals: number;
  /** The channels drawn, per lap. `wheel` is the selected wheel for per-wheel charts. */
  lines: (wheel: Wheel) => LineSpec[];
  /** Fixed y range; omitted = auto. */
  range?: [number, number];
  /** Gear is a discrete signal, so draw it as steps rather than slopes. */
  stepped?: boolean;
  /** Shows the shared wheel selector in the header. */
  perWheel?: boolean;
}

// Order is the top-to-bottom order of the stack (FR-009, FR-010).
const CHARTS: ChartSpec[] = [
  { id: "speed", title: "Speed", unit: "km/h", decimals: 0, lines: () => [{ channel: "speed_kph" }] },
  {
    id: "throttle",
    title: "Throttle",
    unit: "%",
    decimals: 0,
    range: [0, 100],
    lines: () => [{ channel: "throttle", scale: 100 }],
  },
  {
    id: "brake",
    title: "Brake",
    unit: "%",
    decimals: 0,
    range: [0, 100],
    lines: () => [{ channel: "brake", scale: 100 }],
  },
  {
    id: "steer",
    title: "Steering",
    unit: "",
    decimals: 2,
    range: [-1, 1],
    lines: () => [{ channel: "steer" }],
  },
  {
    id: "gear",
    title: "Gear",
    unit: "",
    decimals: 0,
    stepped: true,
    lines: () => [{ channel: "gear" }],
  },
  { id: "rpm", title: "RPM", unit: "rpm", decimals: 0, lines: () => [{ channel: "rpm" }] },
  {
    // One chart for both forces (FR-014): colour tells the lap, dash tells the force.
    id: "g",
    title: "G-force: lateral (solid) and longitudinal (dashed)",
    unit: "g",
    decimals: 2,
    lines: () => [
      { channel: "g_lat", name: "lateral" },
      { channel: "g_lon", name: "longitudinal" },
    ],
  },
  {
    id: "tyre_surface",
    title: "Tyre surface temperature",
    unit: "°C",
    decimals: 1,
    perWheel: true,
    lines: (w) => [{ channel: `tyre_surface_${w}` }],
  },
  {
    id: "brake_temp",
    title: "Brake temperature",
    unit: "°C",
    decimals: 0,
    perWheel: true,
    lines: (w) => [{ channel: `brake_${w}` }],
  },
  {
    id: "gap_ahead",
    title: "Gap to the car ahead",
    unit: "s",
    decimals: 2,
    lines: () => [{ channel: "gap_ahead_ms", scale: 0.001 }],
  },
];

const CHART_HEIGHT = 130;
const DASH = [6, 4];

/**
 * Both laps are sampled on a 1 m grid starting at 0, so index i is the same
 * distance in both. Align by index: x is the longer lap's distance array and the
 * shorter lap's series is padded with null (drawn as a gap, not a line to zero).
 */
function column(trace: LapTrace, line: LineSpec, xs: number[]): (number | null)[] {
  const raw = trace.channels[line.channel];
  const factor = line.scale ?? 1;
  return xs.map((_, i) => {
    const v = raw?.[i];
    return v === undefined || v === null ? null : v * factor;
  });
}

const hasChannel = (trace: LapTrace, line: LineSpec): boolean =>
  (trace.channels[line.channel] ?? []).some((v) => v !== null && v !== undefined);

interface Bands {
  lap: DistanceRun[];
  reference: DistanceRun[];
}

interface ChartProps {
  spec: ChartSpec;
  wheel: Wheel;
  lap: LapTrace;
  reference: LapTrace;
  xs: number[];
  bands: Bands;
  /** Only the chart that reports the cursor gets this. */
  onCursor?: (distance: number | null) => void;
  headerExtra?: ReactNode;
}

const ChannelChart = memo(function ChannelChart({
  spec,
  wheel,
  lap,
  reference,
  xs,
  bands,
  onCursor,
  headerExtra,
}: ChartProps) {
  const built = useMemo(() => {
    const lines = spec.lines(wheel);
    const recorded = lines.some((l) => hasChannel(lap, l) || hasChannel(reference, l));
    const data: uPlot.AlignedData = [
      xs,
      ...[lap, reference].flatMap((t) => lines.map((l) => column(t, l, xs))),
    ];
    const colors = chartColors();
    const fmt = (v: number | null | undefined) =>
      v === null || v === undefined
        ? "—"
        : `${v.toFixed(spec.decimals)}${spec.unit ? ` ${spec.unit}` : ""}`;

    const series = (trace: LapTrace, label: string, stroke: string): uPlot.Series[] =>
      lines.map((l, i) => ({
        label: lines.length > 1 && l.name ? `${label} ${l.name}` : label,
        stroke,
        width: 1.5,
        dash: lines.length > 1 && i > 0 ? DASH : undefined,
        // spanGaps stays false on purpose: null means "not recorded", and joining
        // across it would invent data.
        spanGaps: false,
        value: (_u, v) => fmt(v),
        points: { show: false },
        paths: spec.stepped ? uPlot.paths.stepped?.({ align: 1 }) : undefined,
      }));

    // Off-track stretches (FR-009): faint red over the full height for the compared
    // lap, a thin amber strip along the top for the reference lap.
    const bandsHook = (u: uPlot) => {
      const { ctx, bbox } = u;
      const paint = (runs: DistanceRun[], style: string, top: number, height: number) => {
        ctx.fillStyle = style;
        for (const r of runs) {
          const x0 = u.valToPos(r.from, "x", true);
          const x1 = u.valToPos(Math.max(r.to, r.from + 1), "x", true);
          const left = Math.max(bbox.left, Math.min(x0, x1));
          const right = Math.min(bbox.left + bbox.width, Math.max(x0, x1));
          if (right > left) ctx.fillRect(left, top, right - left, height);
        }
      };
      ctx.save();
      paint(bands.lap, "rgba(229, 72, 77, 0.16)", bbox.top, bbox.height);
      paint(bands.reference, "rgba(232, 179, 57, 0.7)", bbox.top, 4 * devicePixelRatio);
      ctx.restore();
    };

    const hooks: uPlot.Hooks.Arrays = {
      drawClear: [bandsHook],
      draw: [sectorLinesHook(reference.sectors_m, colors.dim)],
    };
    if (onCursor) hooks.setCursor = [cursorDistanceHook(onCursor)];

    const yScale: uPlot.Scale = spec.range
      ? { range: spec.range }
      : spec.stepped
        ? { range: (_u, min, max) => [min - 0.5, max + 0.5] }
        : {};

    const options: ChartOptions = withSync({
      legend: { live: true },
      padding: [8, 12, 0, 0],
      scales: { y: yScale },
      axes: [
        {
          ...axisStyle(colors),
          values: (_u, vals) => vals.map((v) => `${v} m`),
          size: 30,
        },
        {
          ...axisStyle(colors),
          size: Y_AXIS_SIZE,
          // Gear: only whole numbers make sense as ticks.
          values: spec.stepped
            ? (_u, vals) => vals.map((v) => (Number.isInteger(v) ? String(v) : ""))
            : undefined,
        },
      ],
      series: [
        { label: "Distance", value: (_u, v) => (v == null ? "—" : `${v} m`) },
        ...series(lap, `Lap ${lap.lap_number}`, colors.accent),
        ...series(reference, `Ref lap ${reference.lap_number}`, colors.reference),
      ],
      hooks,
    });
    return { options, data, recorded };
  }, [spec, wheel, lap, reference, xs, bands, onCursor]);

  const title = spec.perWheel ? `${spec.title}: ${WHEEL_NAMES[wheel]}` : spec.title;

  return (
    <div className="trace-chart">
      <div className="series-head">
        <div className="chart-title">
          {title}
          {spec.unit ? <span className="unit"> ({spec.unit})</span> : null}
        </div>
        {headerExtra}
      </div>
      {built.recorded ? (
        <UPlotChart options={built.options} data={built.data} height={CHART_HEIGHT} />
      ) : (
        <div className="chart-unavailable" style={{ height: CHART_HEIGHT }}>
          Not recorded for these laps. Laps from a session ingested before this channel existed need
          the ingest to be run again.
        </div>
      )}
    </div>
  );
});

interface Props {
  lap: LapTrace;
  reference: LapTrace;
  /** Reports the distance under the pointer (null when it leaves), for the track map. */
  onCursor?: (distance: number | null) => void;
}

function TraceChartsImpl({ lap, reference, onCursor }: Props) {
  // Keep the latest callback in a ref so a new function identity from the parent
  // does not rebuild every chart.
  const onCursorRef = useRef(onCursor);
  onCursorRef.current = onCursor;
  const reportCursor = useCallback((d: number | null) => onCursorRef.current?.(d), []);

  const [wheel, setWheel] = useState<Wheel>("fl");

  const xs = useMemo(
    () =>
      lap.channels.distance_m.length >= reference.channels.distance_m.length
        ? lap.channels.distance_m
        : reference.channels.distance_m,
    [lap, reference],
  );
  const bands = useMemo<Bands>(
    () => ({ lap: offTrackRuns(lap), reference: offTrackRuns(reference) }),
    [lap, reference],
  );
  const offTrackRecorded = Boolean(lap.channels.off_track || reference.channels.off_track);

  const wheelSelector = (
    <div className="segmented" role="group" aria-label="Wheel">
      {WHEELS.map((w) => (
        <button
          key={w}
          type="button"
          className={w === wheel ? "active" : ""}
          title={WHEEL_NAMES[w]}
          onClick={() => setWheel(w)}
        >
          {w.toUpperCase()}
        </button>
      ))}
    </div>
  );

  return (
    <div className="trace-stack">
      {offTrackRecorded ? (
        <div className="chart-caption" style={{ margin: "0 0 2px" }}>
          <span className="band-key lap" /> Red band: compared lap off track.{" "}
          <span className="band-key ref" /> Amber strip along the top: reference lap off track.
        </div>
      ) : null}
      {CHARTS.map((spec, index) => (
        <ChannelChart
          key={spec.id}
          spec={spec}
          wheel={wheel}
          lap={lap}
          reference={reference}
          xs={xs}
          bands={bands}
          // One chart is enough to observe the (synced) cursor.
          onCursor={index === 0 ? reportCursor : undefined}
          headerExtra={spec.perWheel ? wheelSelector : undefined}
        />
      ))}
    </div>
  );
}

export const TraceCharts = memo(TraceChartsImpl);
