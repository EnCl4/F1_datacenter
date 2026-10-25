import { useEffect, useMemo, useState } from "react";
import { api, type EventRow, type TimelineData, type TyreSetRow } from "./api";
import { SeriesChart, type ChartSeries } from "./charts/SeriesChart";
import { chartColors } from "./charts/theme";

const minutes = (v: number): string => `${Math.round(v)} min`;

function formatClock(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

/** "+0.350 s" / "-0.350 s": the game's estimate against the fitted set, negative = faster. */
function signedSeconds(ms: number | null): string {
  if (ms === null) return "—";
  const s = ms / 1000;
  return `${s > 0 ? "+" : s < 0 ? "-" : ""}${Math.abs(s).toFixed(3)} s`;
}

function Conditions({ data }: { data: TimelineData }) {
  const chart = useMemo(() => {
    if (data.conditions.length === 0) return null;
    const colors = chartColors();
    const rows = [...data.conditions].sort((a, b) => a.session_time_s - b.session_time_s);
    const last = rows[rows.length - 1];
    // The table holds one row per change, so extend the final value to the end of the
    // session (last event or condition) or the step line would stop at the last change.
    const end = Math.max(last.session_time_s, ...data.events.map((e) => e.session_time_s));
    const points = end > last.session_time_s ? [...rows, { ...last, session_time_s: end }] : rows;
    const xs = points.map((p) => p.session_time_s / 60);
    const series: ChartSeries[] = [
      { label: "Track", color: colors.amber, stepped: true, values: points.map((p) => p.track_temp_c) },
      { label: "Air", color: colors.accent, stepped: true, values: points.map((p) => p.air_temp_c) },
    ];
    return { xs, series, rows };
  }, [data]);

  if (!chart) return <div className="empty">No conditions were recorded for this session.</div>;

  return (
    <>
      <SeriesChart
        title="Track and air temperature"
        unit="°C"
        xs={chart.xs}
        series={chart.series}
        decimals={0}
        xFormat={minutes}
        syncKey="f1dc-timeline"
        height={170}
      />
      <div className="table-scroll" style={{ marginTop: 10 }}>
        <table>
          <thead>
            <tr>
              <th className="left">From</th>
              <th>Lap</th>
              <th className="left">Weather</th>
              <th>Track</th>
              <th>Air</th>
            </tr>
          </thead>
          <tbody>
            {chart.rows.map((c) => (
              <tr key={c.session_time_s}>
                <td className="left">{formatClock(c.session_time_s)}</td>
                <td>{c.lap_number}</td>
                <td className="left">{c.weather}</td>
                <td>{c.track_temp_c}°C</td>
                <td>{c.air_temp_c}°C</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function Events({ events }: { events: EventRow[] }) {
  const [mineOnly, setMineOnly] = useState(false);
  const shown = useMemo(
    () =>
      [...events]
        .filter((e) => !mineOnly || e.involves_player)
        .sort((a, b) => a.session_time_s - b.session_time_s),
    [events, mineOnly],
  );
  const mine = events.filter((e) => e.involves_player).length;

  return (
    <>
      <div className="events-head">
        <h3 className="section-title" style={{ margin: 0 }}>
          Events
        </h3>
        <label className="check">
          <input type="checkbox" checked={mineOnly} onChange={(e) => setMineOnly(e.target.checked)} />
          Only events involving you ({mine})
        </label>
      </div>
      {events.length === 0 ? (
        <div className="empty">No events were recorded for this session.</div>
      ) : (
        <div className="events-list">
          <table>
            <thead>
              <tr>
                <th className="left">Lap</th>
                <th className="left">Time</th>
                <th className="left">Event</th>
                <th className="left">Description</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((e, i) => (
                <tr key={`${e.session_time_s}-${e.code}-${i}`} className={e.involves_player ? "player" : ""}>
                  <td className="left">{e.lap_number}</td>
                  <td className="left">{formatClock(e.session_time_s)}</td>
                  <td className="left">
                    <span className="tag">{e.code}</span>
                  </td>
                  <td className="left">
                    {e.description}
                    {e.involves_player ? <span className="tag race you-tag">you</span> : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

function TyreSets({ uid }: { uid: string }) {
  const [items, setItems] = useState<TyreSetRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setItems(null);
    setError(null);
    api
      .tyreSets(uid)
      .then((r) => !cancelled && setItems([...r.items].sort((a, b) => a.set_index - b.set_index)))
      .catch((e: Error) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [uid]);

  return (
    <>
      <h3 className="section-title" style={{ marginTop: 22 }}>
        Tyre sets
      </h3>
      {error ? (
        <div className="error">{error}</div>
      ) : !items ? (
        <div className="empty">Loading…</div>
      ) : items.length === 0 ? (
        <div className="empty">No tyre sets were recorded for this session.</div>
      ) : (
        <>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th className="left">Set</th>
                  <th className="left">Compound</th>
                  <th>Wear</th>
                  <th className="left">Available</th>
                  <th className="left">Fitted</th>
                  <th title="The game's estimate against the fitted set. Negative = faster.">
                    Lap delta
                  </th>
                  <th title="Usable laps left of the set's life span">Usable life</th>
                </tr>
              </thead>
              <tbody>
                {items.map((t) => (
                  <tr key={t.set_index} className={t.fitted ? "player" : t.available ? "" : "excluded"}>
                    <td className="left">{t.set_index}</td>
                    <td className="left">
                      <span className={`compound ${t.visual_compound}`}>{t.visual_compound}</span>
                      {t.actual_compound && t.actual_compound !== t.visual_compound ? (
                        <span className="reason"> ({t.actual_compound})</span>
                      ) : null}
                    </td>
                    <td>{t.wear_pct}%</td>
                    <td className="left">{t.available ? "Yes" : "No"}</td>
                    <td className="left">{t.fitted ? <span className="tag race">fitted</span> : "—"}</td>
                    <td
                      className={
                        t.lap_delta_ms === null || t.lap_delta_ms === 0
                          ? ""
                          : t.lap_delta_ms < 0
                            ? "faster"
                            : "slower"
                      }
                    >
                      {signedSeconds(t.lap_delta_ms)}
                    </td>
                    <td>
                      {t.usable_life !== null && t.life_span !== null
                        ? `${t.usable_life} / ${t.life_span} laps`
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="chart-caption">
            Lap delta is the game's own estimate against the fitted set: negative is faster.
          </div>
        </>
      )}
    </>
  );
}

export function Timeline({ uid }: { uid: string }) {
  const [data, setData] = useState<TimelineData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError(null);
    api
      .timeline(uid)
      .then((d) => !cancelled && setData(d))
      .catch((e: Error) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [uid]);

  return (
    <>
      {error ? (
        <div className="error">{error}</div>
      ) : !data ? (
        <div className="empty">Loading…</div>
      ) : (
        <>
          <Conditions data={data} />
          <div style={{ marginTop: 22 }}>
            <Events events={data.events} />
          </div>
        </>
      )}
      <TyreSets uid={uid} />
    </>
  );
}
