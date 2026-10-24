import { memo, useMemo } from "react";
import type uPlot from "uplot";
import type { GapSeries, LapTrace } from "../api";
import { UPlotChart } from "./UPlotChart";
import { axisStyle, chartColors, Y_AXIS_SIZE } from "./theme";
import { sectorLinesHook, withSync } from "./sync";

interface Props {
  gap: GapSeries;
  lap: LapTrace;
  reference: LapTrace;
}

/** "+1.203 s" / "-0.412 s". */
function formatGap(seconds: number): string {
  return `${seconds >= 0 ? "+" : "-"}${Math.abs(seconds).toFixed(3)} s`;
}

/**
 * Running time gap (US2): positive means the compared lap is BEHIND the reference
 * at that point on the track. Shares the cursor/zoom sync key with the traces.
 */
function GapChartImpl({ gap, lap, reference }: Props) {
  const seconds = useMemo(
    () => gap.gap_ms.map((v) => (v === null ? null : v / 1000)),
    [gap],
  );
  const finalGap = useMemo(() => {
    for (let i = seconds.length - 1; i >= 0; i--) {
      const v = seconds[i];
      if (v !== null) return v;
    }
    return null;
  }, [seconds]);

  const data = useMemo<uPlot.AlignedData>(() => [gap.distance_m, seconds], [gap, seconds]);

  const options = useMemo(() => {
    const colors = chartColors();
    // The zero line is the reference lap itself; everything is measured against it.
    const zeroLine = (u: uPlot) => {
      const { ctx, bbox } = u;
      const y = Math.round(u.valToPos(0, "y", true));
      if (y < bbox.top || y > bbox.top + bbox.height) return;
      ctx.save();
      ctx.strokeStyle = colors.fg;
      ctx.globalAlpha = 0.55;
      ctx.lineWidth = Math.max(1, devicePixelRatio);
      ctx.beginPath();
      ctx.moveTo(bbox.left, y);
      ctx.lineTo(bbox.left + bbox.width, y);
      ctx.stroke();
      ctx.restore();
    };

    return withSync({
      padding: [8, 12, 0, 0],
      legend: { live: true },
      scales: {
        y: {
          // Always include zero with some room either side.
          range: (_u, min, max) => {
            const pad = Math.max(Math.abs(min), Math.abs(max), 0.1) * 0.15;
            return [Math.min(min, 0) - pad, Math.max(max, 0) + pad];
          },
        },
      },
      axes: [
        {
          ...axisStyle(colors),
          values: (_u, vals) => vals.map((v) => `${v} m`),
          size: 30,
        },
        {
          ...axisStyle(colors),
          size: Y_AXIS_SIZE,
          values: (_u, vals) => vals.map((v) => v.toFixed(2)),
        },
      ],
      series: [
        { label: "Distance", value: (_u, v) => (v == null ? "—" : `${v} m`) },
        {
          label: `Lap ${lap.lap_number} vs ref ${reference.lap_number}`,
          stroke: colors.accent,
          width: 2,
          spanGaps: false,
          points: { show: false },
          value: (_u, v) => (v == null ? "—" : formatGap(v)),
        },
      ],
      hooks: { draw: [zeroLine, sectorLinesHook(reference.sectors_m, colors.dim)] },
    });
  }, [lap.lap_number, reference]);

  return (
    <div className="gap-chart">
      <div className="gap-head">
        <div className="chart-title">Time gap to reference (s)</div>
        {finalGap !== null ? (
          <div className={`gap-final ${finalGap > 0 ? "behind" : "ahead"}`}>
            {formatGap(finalGap)} <span className="at-line">at the line</span>
          </div>
        ) : null}
      </div>
      <div className="chart-caption">
        Above zero = slower than reference (behind). Below zero = faster (ahead).
      </div>
      <UPlotChart options={options} data={data} height={240} />
    </div>
  );
}

export const GapChart = memo(GapChartImpl);
