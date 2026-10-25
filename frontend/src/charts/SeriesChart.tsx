import { memo, useMemo, type ReactNode } from "react";
import uPlot from "uplot";
import { UPlotChart } from "./UPlotChart";
import { axisStyle, chartColors, Y_AXIS_SIZE } from "./theme";
import { withSync } from "./sync";

export interface ChartSeries {
  label: string;
  color: string;
  /** One value per x; null is a gap and is never joined across. */
  values: (number | null)[];
  kind?: "line" | "bars";
  /** Bars only: -1 / 1 draws side by side around the x value, 0 is centred. */
  align?: -1 | 0 | 1;
  dash?: number[];
  stepped?: boolean;
  /** When given, the hover readout shows "avg v · max m" instead of just v. */
  max?: (number | null)[];
  width?: number;
}

interface Props {
  title: string;
  unit?: string;
  caption?: ReactNode;
  headerExtra?: ReactNode;
  xs: number[];
  /** Must be memoised by the caller. */
  series: ChartSeries[];
  decimals?: number;
  /** Formats x ticks and the hover x value. Default: whole lap numbers. */
  xFormat?: (v: number) => string;
  /** Vertical dashed lines at these x values (e.g. laps with a tyre change). */
  markers?: number[];
  yRange?: [number, number];
  includeZero?: boolean;
  /** Smaller value at the top (race position). */
  reverseY?: boolean;
  legend?: boolean;
  height?: number;
  syncKey?: string;
  /** Replaces the chart with this message (nothing recorded). */
  unavailable?: string | null;
  className?: string;
}

export const LAP_SYNC_KEY = "f1dc-laps";

const lapFormat = (v: number) => String(v);

/**
 * A compact uPlot chart against a small x axis (lap number, or session time): lines
 * and/or bars. Used by every per-lap chart of the car, field and timeline views.
 */
function SeriesChartImpl({
  title,
  unit,
  caption,
  headerExtra,
  xs,
  series,
  decimals = 1,
  xFormat = lapFormat,
  markers,
  yRange,
  includeZero,
  reverseY,
  legend = true,
  height = 170,
  syncKey = LAP_SYNC_KEY,
  unavailable,
  className,
}: Props) {
  const data = useMemo<uPlot.AlignedData>(
    () => [xs, ...series.map((s) => s.values)],
    [xs, series],
  );

  const options = useMemo(() => {
    const colors = chartColors();
    const hasBars = series.some((s) => s.kind === "bars");
    const fmt = (v: number | null | undefined) =>
      v === null || v === undefined ? "—" : `${v.toFixed(decimals)}${unit ? ` ${unit}` : ""}`;
    // Room for the outer bars. The same pad on every chart of a sync group matters:
    // see the x range below.
    const xPad = xFormat === lapFormat ? 0.7 : 0;

    const markerHook = (u: uPlot) => {
      if (!markers || markers.length === 0) return;
      const { ctx, bbox } = u;
      ctx.save();
      ctx.strokeStyle = colors.dim;
      ctx.lineWidth = Math.max(1, devicePixelRatio);
      ctx.setLineDash([3 * devicePixelRatio, 4 * devicePixelRatio]);
      for (const m of markers) {
        const x = Math.round(u.valToPos(m, "x", true));
        if (x < bbox.left || x > bbox.left + bbox.width) continue;
        ctx.beginPath();
        ctx.moveTo(x, bbox.top);
        ctx.lineTo(x, bbox.top + bbox.height);
        ctx.stroke();
      }
      ctx.restore();
    };

    const yScale: uPlot.Scale = yRange
      ? { range: yRange }
      : reverseY
        ? {
            dir: -1,
            range: (_u, min, max) => [Math.floor(min) - 0.5, Math.ceil(max) + 0.5],
          }
        : includeZero || hasBars
          ? {
              range: (_u, min, max) => {
                const lo = Math.min(0, min);
                const hi = Math.max(0, max);
                const pad = Math.max((hi - lo) * 0.08, 1e-6);
                return [lo < 0 ? lo - pad : lo, hi > 0 ? hi + pad : hi];
              },
            }
          : {
              // Pad so a flat line is not glued to an edge.
              range: (_u, min, max) => {
                const span = Math.max(max - min, Math.abs(max) * 0.02, 1e-6);
                return [min - span * 0.08, max + span * 0.08];
              },
            };

    const uSeries: uPlot.Series[] = [
      { label: xFormat === lapFormat ? "Lap" : "Time", value: (_u, v) => (v == null ? "—" : xFormat(v)) },
      ...series.map((s): uPlot.Series => {
        const base: uPlot.Series = {
          label: s.label,
          stroke: s.color,
          spanGaps: false,
          points: { show: false },
          value: (_u, v, _si, idx) => {
            if (v == null) return "—";
            if (s.max && idx != null) return `avg ${fmt(v)} · max ${fmt(s.max[idx])}`;
            return fmt(v);
          },
        };
        if (s.kind === "bars") {
          return {
            ...base,
            fill: s.color,
            width: 1,
            paths: uPlot.paths.bars?.({ size: [0.4, 100], align: s.align ?? 0 }),
          };
        }
        return {
          ...base,
          width: s.width ?? 1.75,
          dash: s.dash,
          paths: s.stepped ? uPlot.paths.stepped?.({ align: 1 }) : undefined,
          points: { show: xs.length <= 40, size: 4 },
        };
      }),
    ];

    return withSync(
      {
        legend: { show: legend, live: true },
        padding: [8, 12, 0, 0],
        scales: {
          x: {
            // uPlot applies this to explicit setScale() calls too, and the zoom sync
            // re-sends every change to the other charts. A pad added unconditionally
            // would grow on every hop and ping-pong between charts forever (freezing
            // the page). So pad only the data's own extent; any other range (a zoom
            // copied from another chart) is already padded and is kept as it is.
            range: (u, min, max) => {
              if (min == null || max == null) return [min ?? 0, max ?? 1];
              const d = u.data[0];
              return d.length > 0 && min === d[0] && max === d[d.length - 1]
                ? [min - xPad, max + xPad]
                : [min, max];
            },
          },
          y: yScale,
        },
        axes: [
          {
            ...axisStyle(colors),
            size: 28,
            ...(xFormat === lapFormat
              ? {
                  incrs: [1, 2, 5, 10, 20, 50],
                  values: (_u: uPlot, vals: number[]) =>
                    vals.map((v) => (Number.isInteger(v) ? String(v) : "")),
                }
              : { values: (_u: uPlot, vals: number[]) => vals.map((v) => xFormat(v)) }),
          },
          {
            ...axisStyle(colors),
            size: Y_AXIS_SIZE,
          },
        ],
        series: uSeries,
        hooks: { drawClear: [markerHook] },
      },
      syncKey,
    );
  }, [series, xs, decimals, unit, xFormat, markers, yRange, includeZero, reverseY, legend, syncKey]);

  return (
    <div className={`series-chart${className ? ` ${className}` : ""}`}>
      <div className="series-head">
        <div className="chart-title">
          {title}
          {unit ? <span className="unit"> ({unit})</span> : null}
        </div>
        {headerExtra}
      </div>
      {caption ? <div className="chart-caption">{caption}</div> : null}
      {unavailable ? (
        <div className="chart-unavailable" style={{ height }}>
          {unavailable}
        </div>
      ) : (
        <UPlotChart options={options} data={data} height={height} />
      )}
    </div>
  );
}

export const SeriesChart = memo(SeriesChartImpl);
