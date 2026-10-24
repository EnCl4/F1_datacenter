import { memo, useMemo, useRef } from "react";
import uPlot from "uplot";
import type { ChannelKey, LapTrace } from "../api";
import { UPlotChart } from "./UPlotChart";
import { axisStyle, chartColors, Y_AXIS_SIZE } from "./theme";
import { cursorDistanceHook, sectorLinesHook, withSync, type ChartOptions } from "./sync";

interface ChannelSpec {
  key: ChannelKey;
  title: string;
  unit: string;
  /** Multiplier from the raw value to the displayed one (0..1 -> %). */
  scale?: number;
  decimals: number;
  /** Fixed y range; omitted = auto. */
  range?: [number, number];
  /** Gear is a discrete signal, so draw it as steps rather than slopes. */
  stepped?: boolean;
}

// Order is the top-to-bottom order of the stack (FR-009, FR-010).
const CHANNELS: ChannelSpec[] = [
  { key: "speed_kph", title: "Speed", unit: "km/h", decimals: 0 },
  { key: "throttle", title: "Throttle", unit: "%", scale: 100, decimals: 0, range: [0, 100] },
  { key: "brake", title: "Brake", unit: "%", scale: 100, decimals: 0, range: [0, 100] },
  { key: "steer", title: "Steering", unit: "", decimals: 2, range: [-1, 1] },
  { key: "gear", title: "Gear", unit: "", decimals: 0, stepped: true },
  { key: "rpm", title: "RPM", unit: "rpm", decimals: 0 },
  { key: "g_lat", title: "G-force lateral", unit: "g", decimals: 2 },
  { key: "g_lon", title: "G-force longitudinal", unit: "g", decimals: 2 },
];

const CHART_HEIGHT = 130;

/**
 * Both laps are sampled on a 1 m grid starting at 0, so index i is the same
 * distance in both. Align by index: x is the longer lap's distance array and the
 * shorter lap's series is padded with null (drawn as a gap, not a line to zero).
 */
function alignedData(
  lap: LapTrace,
  reference: LapTrace,
  spec: ChannelSpec,
  xs: number[],
): uPlot.AlignedData {
  const factor = spec.scale ?? 1;
  const column = (trace: LapTrace): (number | null)[] => {
    const raw = trace.channels[spec.key];
    return xs.map((_, i) => {
      const v = raw[i];
      return v === undefined || v === null ? null : v * factor;
    });
  };
  return [xs, column(lap), column(reference)];
}

interface Props {
  lap: LapTrace;
  reference: LapTrace;
  /** Reports the distance under the pointer (null when it leaves), for the track map. */
  onCursor?: (distance: number | null) => void;
}

interface BuiltChart {
  spec: ChannelSpec;
  options: ChartOptions;
  data: uPlot.AlignedData;
}

function TraceChartsImpl({ lap, reference, onCursor }: Props) {
  // Keep the latest callback in a ref so a new function identity from the parent
  // does not rebuild every chart.
  const onCursorRef = useRef(onCursor);
  onCursorRef.current = onCursor;

  const charts = useMemo<BuiltChart[]>(() => {
    const colors = chartColors();
    const xs =
      lap.channels.distance_m.length >= reference.channels.distance_m.length
        ? lap.channels.distance_m
        : reference.channels.distance_m;
    // Sector boundaries come from the reference lap (FR-013).
    const sectorHook = sectorLinesHook(reference.sectors_m, colors.dim);

    return CHANNELS.map((spec, index) => {
      const fmt = (v: number | null | undefined) =>
        v === null || v === undefined
          ? "—"
          : `${v.toFixed(spec.decimals)}${spec.unit ? ` ${spec.unit}` : ""}`;

      const line = (label: string, stroke: string): uPlot.Series => ({
        label,
        stroke,
        width: 1.5,
        // spanGaps stays false on purpose: null means "not recorded", and joining
        // across it would invent data.
        spanGaps: false,
        value: (_u, v) => fmt(v),
        points: { show: false },
        paths: spec.stepped ? uPlot.paths.stepped?.({ align: 1 }) : undefined,
      });

      const hooks: uPlot.Hooks.Arrays = { draw: [sectorHook] };
      // One chart is enough to observe the (synced) cursor.
      if (index === 0) {
        hooks.setCursor = [cursorDistanceHook((d) => onCursorRef.current?.(d))];
      }

      const yScale: uPlot.Scale = spec.range
        ? { range: spec.range }
        : spec.stepped
          ? { range: (_u, min, max) => [min - 0.5, max + 0.5] }
          : {};

      const options = withSync({
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
          line(`Lap ${lap.lap_number}`, colors.accent),
          line(`Ref lap ${reference.lap_number}`, colors.reference),
        ],
        hooks,
      });
      return { spec, options, data: alignedData(lap, reference, spec, xs) };
    });
  }, [lap, reference]);

  return (
    <div className="trace-stack">
      {charts.map(({ spec, options, data }) => (
        <div className="trace-chart" key={spec.key}>
          <div className="chart-title">
            {spec.title}
            {spec.unit ? <span className="unit"> ({spec.unit})</span> : null}
          </div>
          <UPlotChart options={options} data={data} height={CHART_HEIGHT} />
        </div>
      ))}
    </div>
  );
}

export const TraceCharts = memo(TraceChartsImpl);
