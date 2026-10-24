import { memo, useMemo, useRef, useState } from "react";
import type uPlot from "uplot";
import { EXCLUSION_LABELS, formatLapTime, type PaceData } from "../api";
import { UPlotChart } from "./UPlotChart";
import { axisStyle, chartColors, compoundColor, Y_AXIS_SIZE } from "./theme";
import type { ChartOptions } from "./sync";

interface Props {
  pace: PaceData;
  /** Lap number to highlight as the currently compared lap. */
  selectedLap?: number | null;
  onSelectLap: (lapNumber: number) => void;
}

function reasonLabel(reason: string | null): string {
  return EXCLUSION_LABELS[reason ?? ""] ?? reason ?? "does not count";
}

/**
 * Session pace (US3): lap time against lap number. Counting laps are solid points
 * joined by a thin line; non-counting laps are hollow and unjoined, so they cannot
 * be mistaken for pace. Stints are shaded bands labelled with their compound.
 */
function PaceChartImpl({ pace, selectedLap, onSelectLap }: Props) {
  const [hover, setHover] = useState<number | null>(null);
  // Latest callbacks/laps via refs so hooks inside the memoised options stay current.
  const onSelectRef = useRef(onSelectLap);
  onSelectRef.current = onSelectLap;

  const laps = useMemo(
    () => [...pace.laps].sort((a, b) => a.lap_number - b.lap_number),
    [pace],
  );

  const data = useMemo<uPlot.AlignedData>(() => {
    const xs = laps.map((l) => l.lap_number);
    const sec = (ms: number | null) => (ms === null || ms <= 0 ? null : ms / 1000);
    const counting = laps.map((l) => (l.counts ? sec(l.lap_time_ms) : null));
    const other = laps.map((l) => (!l.counts ? sec(l.lap_time_ms) : null));
    return [xs, counting, other];
  }, [laps]);

  const options = useMemo<ChartOptions>(() => {
    const colors = chartColors();
    const lastLap = laps.length ? laps[laps.length - 1].lap_number : 1;

    // drawClear runs before axes and series, so the bands sit behind everything.
    const drawStints = (u: uPlot) => {
      const { ctx, bbox } = u;
      const dpr = devicePixelRatio;
      ctx.save();
      ctx.font = `${11 * dpr}px system-ui, sans-serif`;
      ctx.textBaseline = "top";
      pace.stints.forEach((stint, i) => {
        const end = stint.end_lap ?? lastLap;
        // Half a lap either side so a one-lap stint still has a visible width.
        const x0 = u.valToPos(stint.start_lap - 0.5, "x", true);
        const x1 = u.valToPos(end + 0.5, "x", true);
        const left = Math.max(x0, bbox.left);
        const right = Math.min(x1, bbox.left + bbox.width);
        if (right <= left) return;
        const color = compoundColor(stint.tyre_visual_compound_name);
        ctx.globalAlpha = i % 2 === 0 ? 0.1 : 0.17;
        ctx.fillStyle = color;
        ctx.fillRect(left, bbox.top, right - left, bbox.height);
        ctx.globalAlpha = 0.9;
        ctx.fillStyle = color;
        ctx.fillRect(left, bbox.top, right - left, 2 * dpr);
        ctx.fillStyle = colors.fg;
        ctx.fillText(stint.tyre_visual_compound_name, left + 5 * dpr, bbox.top + 5 * dpr);
      });
      ctx.restore();
    };

    return {
      padding: [10, 14, 0, 0],
      legend: { show: false },
      // Click selects a lap; dragging to zoom would only get in the way here.
      cursor: { drag: { x: false, y: false }, points: { size: 10 } },
      scales: {
        x: {
          time: false,
          range: (_u, min, max) => [min - 0.5, max + 0.5],
        },
      },
      axes: [
        {
          ...axisStyle(colors),
          size: 30,
          // Laps are integers; skip fractional ticks.
          values: (_u, vals) => vals.map((v) => (Number.isInteger(v) ? String(v) : "")),
          incrs: [1, 2, 5, 10, 20],
        },
        {
          ...axisStyle(colors),
          size: Y_AXIS_SIZE + 14,
          values: (_u, vals) => vals.map((v) => formatLapTime(v * 1000)),
        },
      ],
      series: [
        { label: "Lap" },
        {
          label: "Counting",
          stroke: colors.accent,
          width: 1,
          spanGaps: true, // join counting laps across excluded ones
          points: { show: true, size: 8, fill: colors.accent, stroke: colors.accent },
        },
        {
          label: "Not counting",
          stroke: colors.amber,
          // No line: excluded laps are not a trend.
          paths: () => null,
          points: { show: true, size: 8, width: 1.5, stroke: colors.amber, fill: colors.panel },
        },
      ],
      hooks: {
        drawClear: [drawStints],
        ready: [
          (u) => {
            u.over.style.cursor = "pointer";
            // Select the nearest lap to the click position, wherever in the plot the
            // click lands: work from the pointer's x, not from cursor.idx, which is
            // only set while the cursor is snapped to a data point.
            u.over.addEventListener("click", (e) => {
              const rect = u.over.getBoundingClientRect();
              const laps = u.data[0];
              if (laps.length === 0) return;
              const x = u.posToVal(e.clientX - rect.left, "x");
              let nearest = laps[0];
              for (const lap of laps) {
                if (Math.abs(lap - x) < Math.abs(nearest - x)) nearest = lap;
              }
              onSelectRef.current(nearest);
            });
          },
        ],
        setCursor: [
          (u) => {
            const idx = u.cursor.left != null && u.cursor.left >= 0 ? u.cursor.idx ?? null : null;
            setHover((prev) => (prev === idx ? prev : idx));
          },
        ],
      },
    };
  }, [laps, pace.stints]);

  const shown = hover !== null ? laps[hover] : null;
  const unplotted = laps.filter((l) => l.lap_time_ms === null || l.lap_time_ms <= 0);

  return (
    <div className="pace-chart">
      <div className="pace-head">
        <div className="chart-title">Session pace</div>
        <div className="pace-legend">
          <span className="key solid" /> counting
          <span className="key hollow" /> not counting
        </div>
      </div>

      {/* Readout in place of the uPlot legend: it can name the exclusion reason. */}
      <div className="pace-readout">
        {shown ? (
          <>
            <strong>Lap {shown.lap_number}</strong> · {formatLapTime(shown.lap_time_ms)} ·{" "}
            {shown.tyre_visual_compound_name}
            {shown.counts ? null : (
              <span className="reason-pill">not counting: {reasonLabel(shown.exclusion_reason)}</span>
            )}
          </>
        ) : (
          <span className="dim">
            Hover a lap for details
            {selectedLap ? ` · comparing lap ${selectedLap}` : ""} — click to compare it.
          </span>
        )}
      </div>

      <UPlotChart options={options} data={data} height={220} />

      {unplotted.length > 0 ? (
        <div className="chart-caption">
          No time recorded (not plotted):{" "}
          {unplotted
            .map((l) => `lap ${l.lap_number} (${reasonLabel(l.exclusion_reason ?? "incomplete")})`)
            .join(", ")}
        </div>
      ) : null}
    </div>
  );
}

export const PaceChart = memo(PaceChartImpl);
