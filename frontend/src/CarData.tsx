import { useEffect, useMemo, useState } from "react";
import {
  api,
  formatLapTime,
  WHEELS,
  WHEEL_NAMES,
  type LapCarRow,
  type LapRow,
  type Wheel,
} from "./api";
import { SeriesChart, type ChartSeries } from "./charts/SeriesChart";
import { chartColors, WHEEL_DASH, wheelColors } from "./charts/theme";

type TempMode = "surface" | "core";
type WheelPrefix =
  | "tyre_surface_avg"
  | "tyre_surface_max"
  | "tyre_inner_avg"
  | "tyre_inner_max"
  | "brake_avg"
  | "brake_max"
  | "pressure_avg";

/** ERS deploy modes and fuel mixes as the game numbers them (F1 23). */
const ERS_MODE_NAMES: Record<string, string> = {
  "0": "None",
  "1": "Medium",
  "2": "Hotlap",
  "3": "Overtake",
};
const FUEL_MIX_NAMES: Record<string, string> = {
  "0": "Lean",
  "1": "Standard",
  "2": "Rich",
  "3": "Max",
};

/** "1,3" -> "Medium, Overtake". Unknown codes are shown as they came. */
function modeList(raw: string | null, names?: Record<string, string>): string {
  if (raw === null || raw === "") return "—";
  return raw
    .split(",")
    .map((p) => p.trim())
    .map((p) => names?.[p] ?? p)
    .join(", ");
}

const DAMAGE_PARTS = [
  ["damage_front_left_wing", "FL wing", "Front-left wing"],
  ["damage_front_right_wing", "FR wing", "Front-right wing"],
  ["damage_rear_wing", "Rear wing", "Rear wing"],
  ["damage_floor", "Floor", "Floor"],
  ["damage_diffuser", "Diffuser", "Diffuser"],
  ["damage_sidepod", "Sidepod", "Sidepod"],
  ["damage_gearbox", "Gearbox", "Gearbox"],
  ["damage_engine", "Engine", "Engine"],
] as const;

const gapText = (ms: number | null, position: number | null): string => {
  if (ms === null) return position === 1 ? "leader" : "—";
  return `+${(ms / 1000).toFixed(3)} s`;
};

function wheelValues(rows: LapCarRow[], prefix: WheelPrefix, wheel: Wheel): (number | null)[] {
  return rows.map((r) => r[`${prefix}_${wheel}` as const]);
}

function CarTable({ rows, laps }: { rows: LapCarRow[]; laps: Map<number, LapRow> }) {
  const peakExcursions = Math.max(0, ...rows.map((r) => r.excursions ?? 0));

  return (
    <>
      <h3 className="section-title">Settings and condition per lap</h3>
      <div className="table-scroll">
        <table className="car-table">
          <thead>
            <tr>
              <th className="left">Lap</th>
              <th>Time</th>
              <th className="left">Tyre</th>
              <th>Pos</th>
              <th>Gap ahead</th>
              <th>Brake bias</th>
              <th className="left">ERS mode</th>
              <th className="left">Fuel mix</th>
              <th>Fuel left</th>
              {DAMAGE_PARTS.map(([key, label, title]) => (
                <th key={key} title={`${title} damage (%)`}>
                  {label}
                </th>
              ))}
              <th title="Times a wheel left the track">Exc.</th>
              <th title="Corner-cutting warnings">Warn</th>
              <th title="Penalty seconds">Pen</th>
              <th className="left">Notes</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => {
              const prev = i > 0 ? rows[i - 1] : null;
              const lap = laps.get(row.lap_number);
              const changed = (a: string | null, b: string | null | undefined) =>
                row.settings_changed && (prev === null || (a ?? "") !== (b ?? ""));
              const bbChanged = changed(row.brake_bias, prev?.brake_bias);
              const ersChanged = changed(row.ers_modes, prev?.ers_modes);
              const mixChanged = changed(row.fuel_mix, prev?.fuel_mix);
              return (
                <tr key={row.lap_number} className={lap && !lap.counts ? "excluded" : ""}>
                  <td className="left">{row.lap_number}</td>
                  <td className="time">{formatLapTime(lap?.lap_time_ms)}</td>
                  <td className="left">
                    {lap ? (
                      <span className={`compound ${lap.tyre_visual_compound_name}`}>
                        {lap.tyre_visual_compound_name}
                      </span>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td>{row.position_at_line ?? "—"}</td>
                  <td>{gapText(row.gap_ahead_ms_at_line, row.position_at_line)}</td>
                  <td
                    className={bbChanged ? "changed" : ""}
                    title={bbChanged ? "Changed on this lap" : undefined}
                  >
                    {row.brake_bias ? `${row.brake_bias.split(",").join(" → ")} %` : "—"}
                  </td>
                  <td
                    className={`left${ersChanged ? " changed" : ""}`}
                    title={ersChanged ? "Changed on this lap" : undefined}
                  >
                    {modeList(row.ers_modes, ERS_MODE_NAMES)}
                  </td>
                  <td
                    className={`left${mixChanged ? " changed" : ""}`}
                    title={mixChanged ? "Changed on this lap" : undefined}
                  >
                    {modeList(row.fuel_mix, FUEL_MIX_NAMES)}
                  </td>
                  <td>{row.fuel_end_kg === null ? "—" : `${row.fuel_end_kg.toFixed(1)} kg`}</td>
                  {DAMAGE_PARTS.map(([key, , title]) => {
                    const value = row[key];
                    const increased =
                      row.damage_increased && value !== null && value > (prev?.[key] ?? 0);
                    return (
                      <td
                        key={key}
                        className={increased ? "damaged" : value ? "" : "zero"}
                        title={increased ? `${title} damage increased on this lap` : undefined}
                      >
                        {value === null ? "—" : `${value}%`}
                      </td>
                    );
                  })}
                  <td
                    className={
                      peakExcursions > 0 && row.excursions === peakExcursions ? "damaged" : ""
                    }
                    title={row.excursion_m ? `${row.excursion_m.toFixed(0)} m off track` : undefined}
                  >
                    {row.excursions ?? "—"}
                  </td>
                  <td>{row.corner_warnings ?? "—"}</td>
                  <td>{row.penalties_s ? `+${row.penalties_s} s` : (row.penalties_s ?? "—")}</td>
                  <td className="left notes">
                    {row.tyre_change_in_lap ? <span className="tag warn">tyre change</span> : null}
                    {lap?.is_in_lap ? <span className="tag">in lap</span> : null}
                    {lap?.is_out_lap ? <span className="tag">out lap</span> : null}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="chart-caption">
        Amber = setting changed on that lap. Red = part damage increased on that lap, or the lap with
        the most track-limit excursions. On tyre-change laps the temperatures cover the set fitted
        at the start of the lap only.
      </div>
    </>
  );
}

export function CarData({ uid, laps }: { uid: string; laps: LapRow[] }) {
  const [rows, setRows] = useState<LapCarRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [temp, setTemp] = useState<TempMode>("surface");

  useEffect(() => {
    let cancelled = false;
    setRows(null);
    setError(null);
    api
      .car(uid)
      .then((r) => !cancelled && setRows([...r.laps].sort((a, b) => a.lap_number - b.lap_number)))
      .catch((e: Error) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [uid]);

  const lapsByNumber = useMemo(() => new Map(laps.map((l) => [l.lap_number, l])), [laps]);

  const charts = useMemo(() => {
    if (!rows) return null;
    const colors = chartColors();
    const wc = wheelColors(colors);
    const perWheel = (
      values: (w: Wheel) => (number | null)[],
      max?: (w: Wheel) => (number | null)[],
    ): ChartSeries[] =>
      WHEELS.map((w) => ({
        label: WHEEL_NAMES[w],
        color: wc[w],
        dash: WHEEL_DASH[w],
        values: values(w),
        max: max?.(w),
      }));

    const xs = rows.map((r) => r.lap_number);
    const col = (pick: (r: LapCarRow) => number | null) => rows.map(pick);
    const deficit = col((r) =>
      r.ers_balance_mj === null ? null : r.ers_balance_mj < 0 ? r.ers_balance_mj : null,
    );
    const surplus = col((r) =>
      r.ers_balance_mj === null ? null : r.ers_balance_mj >= 0 ? r.ers_balance_mj : null,
    );

    const battery: ChartSeries[] = [
      { label: "Lap start", color: colors.accent, values: col((r) => r.ers_start_mj) },
      { label: "Lap end", color: colors.amber, values: col((r) => r.ers_end_mj), dash: [6, 4] },
    ];
    const flow: ChartSeries[] = [
      {
        label: "Deployed",
        color: colors.amber,
        kind: "bars",
        align: -1,
        values: col((r) => r.ers_deployed_mj),
      },
      {
        label: "Harvested",
        color: colors.green,
        kind: "bars",
        align: 1,
        values: col((r) => r.ers_harvested_mj),
      },
    ];
    const balance: ChartSeries[] = [
      { label: "Surplus", color: colors.green, kind: "bars", values: surplus },
      { label: "Deficit", color: colors.red, kind: "bars", values: deficit },
    ];
    const fuel: ChartSeries[] = [
      { label: "Fuel used", color: colors.accent, kind: "bars", values: col((r) => r.fuel_used_kg) },
    ];
    const position: ChartSeries[] = [
      {
        label: "Position",
        color: colors.accent,
        stepped: true,
        values: col((r) => r.position_at_line),
      },
    ];
    const gap: ChartSeries[] = [
      {
        label: "Gap ahead",
        color: colors.amber,
        values: col((r) =>
          r.gap_ahead_ms_at_line === null ? null : r.gap_ahead_ms_at_line / 1000,
        ),
      },
    ];

    return {
      xs,
      markers: rows.filter((r) => r.tyre_change_in_lap).map((r) => r.lap_number),
      surface: perWheel(
        (w) => wheelValues(rows, "tyre_surface_avg", w),
        (w) => wheelValues(rows, "tyre_surface_max", w),
      ),
      core: perWheel(
        (w) => wheelValues(rows, "tyre_inner_avg", w),
        (w) => wheelValues(rows, "tyre_inner_max", w),
      ),
      brake: perWheel((w) => wheelValues(rows, "brake_max", w)),
      pressure: perWheel((w) => wheelValues(rows, "pressure_avg", w)),
      battery,
      flow,
      balance,
      fuel,
      position,
      gap,
    };
  }, [rows]);

  // Tyre wear comes from the existing laps endpoint, so it renders even when the car
  // endpoint is unavailable.
  const wear = useMemo(() => {
    const colors = chartColors();
    const wc = wheelColors(colors);
    const sorted = [...laps].sort((a, b) => a.lap_number - b.lap_number);
    const pick = (l: LapRow, w: Wheel): number | null =>
      ({ fl: l.tyre_wear_fl, fr: l.tyre_wear_fr, rl: l.tyre_wear_rl, rr: l.tyre_wear_rr })[w];
    return {
      xs: sorted.map((l) => l.lap_number),
      series: WHEELS.map(
        (w): ChartSeries => ({
          label: WHEEL_NAMES[w],
          color: wc[w],
          dash: WHEEL_DASH[w],
          values: sorted.map((l) => pick(l, w)),
        }),
      ),
    };
  }, [laps]);

  const tempToggle = (
    <div className="segmented" role="group" aria-label="Tyre temperature source">
      {(["surface", "core"] as const).map((m) => (
        <button
          key={m}
          type="button"
          className={m === temp ? "active" : ""}
          onClick={() => setTemp(m)}
        >
          {m === "surface" ? "Surface" : "Core"}
        </button>
      ))}
    </div>
  );

  const wearChart = (
    <SeriesChart
      title="Tyre wear"
      unit="%"
      xs={wear.xs}
      series={wear.series}
      decimals={1}
      includeZero
      caption="Resets to near zero at each tyre change."
    />
  );

  if (error) {
    return (
      <>
        <div className="error">{error}</div>
        <div className="chart-grid" style={{ marginTop: 14 }}>
          {wearChart}
        </div>
      </>
    );
  }
  if (!rows || !charts) return <div className="empty">Loading…</div>;
  if (rows.length === 0) return <div className="empty">No car data was recorded for this session.</div>;

  const tempSeries = temp === "surface" ? charts.surface : charts.core;

  return (
    <>
      <div className="chart-grid">
        <SeriesChart
          title={`Tyre ${temp} temperature`}
          unit="°C"
          xs={charts.xs}
          series={tempSeries}
          decimals={1}
          markers={charts.markers}
          headerExtra={tempToggle}
          caption="Average per lap; hover for the average and the peak. Dashed vertical line = tyre change."
        />
        <SeriesChart
          title="Brake temperature (peak per lap)"
          unit="°C"
          xs={charts.xs}
          series={charts.brake}
          decimals={0}
          markers={charts.markers}
        />
        <SeriesChart
          title="Tyre pressure (average per lap)"
          unit="psi"
          xs={charts.xs}
          series={charts.pressure}
          decimals={1}
          markers={charts.markers}
        />
        {wearChart}
        <SeriesChart
          title="Battery charge"
          unit="MJ"
          xs={charts.xs}
          series={charts.battery}
          decimals={2}
          includeZero
        />
        <SeriesChart
          title="Energy deployed and harvested per lap"
          unit="MJ"
          xs={charts.xs}
          series={charts.flow}
          decimals={2}
          includeZero
        />
        <SeriesChart
          title="Energy balance per lap"
          unit="MJ"
          xs={charts.xs}
          series={charts.balance}
          decimals={2}
          includeZero
          caption="Harvested minus deployed. Red bars: more energy deployed than harvested."
        />
        <SeriesChart
          title="Fuel used per lap"
          unit="kg"
          xs={charts.xs}
          series={charts.fuel}
          decimals={2}
          includeZero
        />
        <SeriesChart
          title="Position at the line"
          xs={charts.xs}
          series={charts.position}
          decimals={0}
          reverseY
        />
        <SeriesChart
          title="Gap to the car ahead at the line"
          unit="s"
          xs={charts.xs}
          series={charts.gap}
          decimals={3}
          includeZero
        />
      </div>

      <CarTable rows={rows} laps={lapsByNumber} />
    </>
  );
}
