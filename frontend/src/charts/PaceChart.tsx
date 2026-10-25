import { memo, useMemo, useRef, useState } from "react";
import uPlot from "uplot";
import { EXCLUSION_LABELS, formatLapTime, type PaceData } from "../api";
import { UPlotChart } from "./UPlotChart";
import { axisStyle, chartColors, compoundColor, Y_AXIS_SIZE } from "./theme";
import type { ChartOptions } from "./sync";
import {
  allRange,
  averageSegments,
  formatRangeInput,
  movingAverage,
  parseLapInput,
  validRange,
} from "./pace";

type YMode = "valid" | "all" | "manual";
const Y_MODES: { id: YMode; label: string }[] = [
  { id: "valid", label: "Valid laps" },
  { id: "all", label: "All laps" },
  { id: "manual", label: "Manual" },
];
const AVG_WINDOWS = [0, 3, 5, 10];

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
 *
 * The y range defaults to the counting laps so pit/out laps do not flatten the real
 * pace; laps beyond it are drawn as triangles on the plot edge. An optional rolling
 * mean (counting laps only, restarted every stint) is drawn as a green line.
 */
function PaceChartImpl({ pace, selectedLap, onSelectLap }: Props) {
  const [hover, setHover] = useState<number | null>(null);
  const [yMode, setYMode] = useState<YMode>("valid");
  const [avgWindow, setAvgWindow] = useState(3);
  const [manual, setManual] = useState<[number, number] | null>(null);
  const [minText, setMinText] = useState("");
  const [maxText, setMaxText] = useState("");
  const [badMin, setBadMin] = useState(false);
  const [badMax, setBadMax] = useState(false);
  // Latest callbacks/laps via refs so hooks inside the memoised options stay current.
  const onSelectRef = useRef(onSelectLap);
  onSelectRef.current = onSelectLap;

  const laps = useMemo(
    () => [...pace.laps].sort((a, b) => a.lap_number - b.lap_number),
    [pace],
  );

  const average = useMemo(
    () => (avgWindow > 0 ? movingAverage(laps, avgWindow, pace.stints) : laps.map(() => null)),
    [laps, avgWindow, pace.stints],
  );
  const segments = useMemo(
    () => (avgWindow > 0 ? averageSegments(laps, average, pace.stints) : []),
    [laps, average, avgWindow, pace.stints],
  );

  /** y range in seconds, or null to let uPlot auto-fit every lap. */
  const baseRange = useMemo(
    () => (yMode === "all" ? null : validRange(laps)),
    [yMode, laps],
  );
  const yRange = yMode === "manual" ? manual ?? baseRange : baseRange;

  const data = useMemo<uPlot.AlignedData>(() => {
    const xs = laps.map((l) => l.lap_number);
    const sec = (ms: number | null) => (ms === null || ms <= 0 ? null : ms / 1000);
    const counting = laps.map((l) => (l.counts ? sec(l.lap_time_ms) : null));
    const other = laps.map((l) => (!l.counts ? sec(l.lap_time_ms) : null));
    return [xs, counting, other, ...segments];
  }, [laps, segments]);

  const yLo = yRange ? yRange[0] : null;
  const yHi = yRange ? yRange[1] : null;

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

    // Laps outside the y range would silently vanish; mark them with a triangle on the
    // top/bottom edge instead (same colour as the non-counting points).
    const drawOffScale = (u: uPlot) => {
      const { ctx, bbox } = u;
      const { min, max } = u.scales.y;
      if (min == null || max == null) return;
      const dpr = devicePixelRatio;
      const half = 4.5 * dpr;
      const h = 7 * dpr;
      ctx.save();
      ctx.fillStyle = colors.amber;
      const xs = u.data[0];
      for (let i = 0; i < xs.length; i++) {
        const v = (u.data[1][i] ?? u.data[2][i]) as number | null | undefined;
        if (v == null) continue;
        const above = v > max;
        if (!above && v >= min) continue;
        const cx = u.valToPos(xs[i], "x", true);
        if (cx < bbox.left || cx > bbox.left + bbox.width) continue;
        ctx.beginPath();
        if (above) {
          const y = bbox.top + 1 * dpr;
          ctx.moveTo(cx - half, y + h);
          ctx.lineTo(cx + half, y + h);
          ctx.lineTo(cx, y);
        } else {
          const y = bbox.top + bbox.height - 1 * dpr;
          ctx.moveTo(cx - half, y - h);
          ctx.lineTo(cx + half, y - h);
          ctx.lineTo(cx, y);
        }
        ctx.closePath();
        ctx.fill();
      }
      ctx.restore();
    };

    const spline = uPlot.paths.spline?.();
    const avgSeries: uPlot.Series[] = segments.map((_, i) => ({
      // One series per stint so no line is drawn across a pit stop.
      label: i === 0 ? `Avg (${avgWindow} laps)` : `Avg (${avgWindow} laps) · stint ${i + 1}`,
      stroke: colors.green,
      width: 2,
      spanGaps: true,
      ...(spline ? { paths: spline } : {}),
      points: { show: false },
    }));

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
        y:
          yLo !== null && yHi !== null
            ? { auto: false, range: () => [yLo, yHi] as [number, number] }
            : {},
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
        ...avgSeries,
      ],
      hooks: {
        drawClear: [drawStints],
        draw: [drawOffScale],
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
  }, [laps, pace.stints, segments, avgWindow, yLo, yHi]);

  // --- y-axis controls -------------------------------------------------------
  const chooseMode = (mode: YMode) => {
    if (mode === "manual") {
      // Pre-fill from whatever range is showing now.
      const cur = yRange ?? allRange(laps);
      if (cur) {
        setManual([cur[0], cur[1]]);
        setMinText(formatRangeInput(cur[0]));
        setMaxText(formatRangeInput(cur[1]));
      }
      setBadMin(false);
      setBadMax(false);
    }
    setYMode(mode);
  };

  const commit = (which: "min" | "max") => {
    const text = which === "min" ? minText : maxText;
    const setBad = which === "min" ? setBadMin : setBadMax;
    const value = parseLapInput(text);
    const cur = manual ?? baseRange ?? allRange(laps);
    const other = cur ? (which === "min" ? cur[1] : cur[0]) : null;
    const ok =
      value !== null && (other === null || (which === "min" ? value < other : value > other));
    if (!ok || value === null) {
      setBad(true);
      return;
    }
    setBad(false);
    (which === "min" ? setMinText : setMaxText)(formatRangeInput(value));
    setManual(which === "min" ? [value, other ?? value + 1] : [other ?? value - 1, value]);
  };

  const rangeInput = (which: "min" | "max") => {
    const bad = which === "min" ? badMin : badMax;
    return (
      <label className="range-field">
        {which === "min" ? "Min" : "Max"}
        <input
          type="text"
          inputMode="decimal"
          className={bad ? "bad" : ""}
          value={which === "min" ? minText : maxText}
          aria-invalid={bad}
          placeholder="1:20.5"
          onChange={(e) => (which === "min" ? setMinText : setMaxText)(e.target.value)}
          onBlur={() => commit(which)}
          onKeyDown={(e) => {
            if (e.key === "Enter") commit(which);
          }}
        />
      </label>
    );
  };

  const shown = hover !== null ? laps[hover] : null;
  const shownAvg = hover !== null ? average[hover] : null;
  const shownTime = shown && shown.lap_time_ms !== null && shown.lap_time_ms > 0 ? shown.lap_time_ms / 1000 : null;
  const offScale =
    shownTime !== null && yLo !== null && yHi !== null && (shownTime < yLo || shownTime > yHi);
  const unplotted = laps.filter((l) => l.lap_time_ms === null || l.lap_time_ms <= 0);

  return (
    <div className="pace-chart">
      <div className="pace-head">
        <div className="chart-title">Session pace</div>
        <div className="pace-legend">
          <span className="key solid" /> counting
          <span className="key hollow" /> not counting
          {segments.length > 0 ? (
            <>
              <span className="key line" /> Avg ({avgWindow} laps)
            </>
          ) : null}
          {yMode !== "all" ? (
            <>
              <span className="key tri" /> off scale
            </>
          ) : null}
        </div>
      </div>

      <div className="pace-controls">
        <div className="control-group">
          <span className="control-label">Y axis</span>
          <div className="segmented">
            {Y_MODES.map((m) => (
              <button
                key={m.id}
                type="button"
                className={yMode === m.id ? "active" : ""}
                onClick={() => chooseMode(m.id)}
              >
                {m.label}
              </button>
            ))}
          </div>
          {yMode === "manual" ? (
            <>
              {rangeInput("min")}
              {rangeInput("max")}
            </>
          ) : null}
        </div>
        <div className="control-group">
          <span className="control-label">Average</span>
          <div className="segmented">
            {AVG_WINDOWS.map((w) => (
              <button
                key={w}
                type="button"
                className={avgWindow === w ? "active" : ""}
                onClick={() => setAvgWindow(w)}
              >
                {w === 0 ? "Off" : w}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Readout in place of the uPlot legend: it can name the exclusion reason. */}
      <div className="pace-readout">
        {shown ? (
          <>
            <strong>Lap {shown.lap_number}</strong> · {formatLapTime(shown.lap_time_ms)} ·{" "}
            {shown.tyre_visual_compound_name}
            {shownAvg !== null ? (
              <span className="avg-pill">
                avg ({avgWindow}) {formatLapTime(shownAvg * 1000)}
              </span>
            ) : null}
            {offScale ? <span className="dim"> · off scale</span> : null}
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
