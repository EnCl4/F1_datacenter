import { useEffect, useMemo, useState } from "react";
import { api, formatLapTime, type FieldCar, type FieldData } from "./api";
import { SeriesChart, type ChartSeries } from "./charts/SeriesChart";
import { chartColors } from "./charts/theme";

const byBestLap = (a: FieldCar, b: FieldCar): number => {
  if (a.best_lap_ms === null && b.best_lap_ms === null) return 0;
  if (a.best_lap_ms === null) return 1;
  if (b.best_lap_ms === null) return -1;
  return a.best_lap_ms - b.best_lap_ms;
};

function percentile(sorted: number[], p: number): number {
  return sorted[Math.min(sorted.length - 1, Math.max(0, Math.floor(p * (sorted.length - 1))))];
}

/** Every car's lap times against lap number: the player in colour, rivals in grey. */
function FieldPace({ data }: { data: FieldData }) {
  const prepared = useMemo(() => {
    const colors = chartColors();
    const valid = data.laps.filter((l) => l.valid && l.lap_time_ms !== null && l.lap_time_ms > 0);
    if (valid.length === 0) return null;
    const maxLap = Math.max(...valid.map((l) => l.lap_number));
    const xs = Array.from({ length: maxLap }, (_, i) => i + 1);
    const byCar = new Map<number, (number | null)[]>();
    for (const l of valid) {
      let col = byCar.get(l.car_idx);
      if (!col) {
        col = xs.map(() => null);
        byCar.set(l.car_idx, col);
      }
      col[l.lap_number - 1] = (l.lap_time_ms ?? 0) / 1000;
    }
    const times = valid.map((l) => (l.lap_time_ms ?? 0) / 1000).sort((a, b) => a - b);
    // Pit laps and safety cars would flatten everything, so zoom on the racing laps.
    const range: [number, number] = [percentile(times, 0.01) - 0.5, percentile(times, 0.9) + 1];

    const rivals: ChartSeries[] = [];
    let playerSeries: ChartSeries | null = null;
    for (const car of data.cars) {
      const values = byCar.get(car.car_idx);
      if (!values) continue;
      if (car.is_player) {
        playerSeries = { label: `${car.name} (you)`, color: colors.accent, values, width: 2.5 };
      } else {
        rivals.push({ label: car.name, color: colors.line, values, width: 1 });
      }
    }
    const series = playerSeries ? [...rivals, playerSeries] : rivals;
    return { xs, series, range };
  }, [data]);

  if (!prepared) return null;
  return (
    <SeriesChart
      title="Lap times: you against the field"
      unit="s"
      xs={prepared.xs}
      series={prepared.series}
      decimals={3}
      yRange={prepared.range}
      legend={false}
      height={220}
      syncKey="f1dc-field"
      caption="Blue = you, grey = every rival. Valid laps only; pit laps and slow laps fall above the range shown."
    />
  );
}

export function Field({ uid }: { uid: string }) {
  const [data, setData] = useState<FieldData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError(null);
    api
      .field(uid)
      .then((d) => !cancelled && setData(d))
      .catch((e: Error) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [uid]);

  const cars = useMemo(() => (data ? [...data.cars].sort(byBestLap) : []), [data]);

  if (error) return <div className="error">{error}</div>;
  if (!data) return <div className="empty">Loading…</div>;
  if (cars.length === 0) return <div className="empty">No other cars were recorded in this session.</div>;

  const fastest = cars.find((c) => c.best_lap_ms !== null)?.best_lap_ms ?? null;
  const player = cars.find((c) => c.is_player);

  return (
    <>
      <div className="rank-banner">
        {data.player_rank !== null ? (
          <>
            <strong>Your best lap ranks {data.player_rank} of {cars.length}</strong>
            {player?.best_lap_ms ? (
              <span className="dim">
                {" "}
                · {formatLapTime(player.best_lap_ms)}
                {fastest !== null && player.best_lap_ms !== fastest
                  ? ` · +${((player.best_lap_ms - fastest) / 1000).toFixed(3)} s to the fastest lap of ${formatLapTime(fastest)}`
                  : " · the fastest lap of the session"}
              </span>
            ) : null}
          </>
        ) : (
          <strong>Your best lap is not ranked: no counting lap was recorded.</strong>
        )}
      </div>

      <FieldPace data={data} />

      <h3 className="section-title" style={{ marginTop: 18 }}>
        Best laps
      </h3>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th className="left">Rank</th>
              <th className="left">Driver</th>
              <th>No.</th>
              <th>Best lap</th>
              <th>Gap to fastest</th>
              <th>Best on lap</th>
              <th>Laps</th>
              <th>Finish</th>
              <th className="left">Stints</th>
            </tr>
          </thead>
          <tbody>
            {cars.map((car, i) => {
              const ranked = car.best_lap_ms !== null;
              return (
                <tr key={car.car_idx} className={car.is_player ? "player" : ""}>
                  <td className="left">{ranked ? i + 1 : "—"}</td>
                  <td className="left">
                    {car.name}
                    {car.is_player ? <span className="tag race you-tag">you</span> : null}
                  </td>
                  <td>{car.race_number}</td>
                  <td className="time">{formatLapTime(car.best_lap_ms)}</td>
                  <td>
                    {ranked && fastest !== null && car.best_lap_ms !== fastest
                      ? `+${(((car.best_lap_ms ?? 0) - fastest) / 1000).toFixed(3)}`
                      : ranked
                        ? "fastest"
                        : "—"}
                  </td>
                  <td>{car.best_lap_number ?? "—"}</td>
                  <td>{car.num_laps}</td>
                  <td title={car.result_status || undefined}>
                    {car.finish_position ?? (car.result_status ? car.result_status : "—")}
                  </td>
                  <td className="left stints-cell">{car.stints || "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}
