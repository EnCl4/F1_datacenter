import { useEffect, useState } from "react";
import {
  api,
  EXCLUSION_LABELS,
  formatDate,
  formatDuration,
  formatLapTime,
  formatSector,
  type LapRow,
  type SessionDetail as Detail,
  type StintRow,
} from "./api";

/**
 * FR-022: the comparability context sits beside the lap times, not behind a menu.
 *
 * Traction control and ABS come from a different packet than the other assists. Showing
 * only the Session packet's nine would report "no assists" for a driver running full TC,
 * which is exactly the misrepresentation principle VI exists to prevent.
 */
function ContextPanel({ session }: { session: Detail }) {
  const a = session.assists;
  const cell = (k: string, v: React.ReactNode, warn = false) => (
    <div className="cell" key={k}>
      <div className="k">{k}</div>
      <div className={`v${warn ? " warn" : ""}`}>{v}</div>
    </div>
  );

  return (
    <div className="context">
      {cell("Weather", session.conditions.weather_name)}
      {cell("Track temp", `${session.conditions.track_temp_c}°C`)}
      {cell("Air temp", `${session.conditions.air_temp_c}°C`)}
      {cell("AI difficulty", session.ai_difficulty)}
      {cell("Traction control", a.traction_control === 0 ? "Off" : a.traction_control === 1 ? "Medium" : "Full", a.traction_control > 0)}
      {cell("ABS", a.anti_lock_brakes ? "On" : "Off", a.anti_lock_brakes > 0)}
      {cell("Gearbox", a.gearbox <= 1 ? "Manual" : "Automatic", a.gearbox > 1)}
      {cell("Steering assist", a.steering ? "On" : "Off", a.steering > 0)}
      {cell("Braking assist", a.braking ? "On" : "Off", a.braking > 0)}
      {cell("Racing line", a.racing_line ? "On" : "Off", a.racing_line > 0)}
      {cell("Recording loss", `${session.loss_pct.toFixed(2)}%`, session.loss_pct > 1)}
      {cell("Ended", session.end_reason.replace("_", " "), !session.ended_naturally)}
    </div>
  );
}

function LapTable({ laps, bestLap }: { laps: LapRow[]; bestLap: number | null }) {
  return (
    <table>
      <thead>
        <tr>
          <th className="left">Lap</th>
          <th>Time</th>
          <th>S1</th>
          <th>S2</th>
          <th>S3</th>
          <th className="left">Tyre</th>
          <th>Age</th>
          <th>Wear FL/FR</th>
          <th>Wear RL/RR</th>
          <th>Pos</th>
          <th className="left">Counts</th>
        </tr>
      </thead>
      <tbody>
        {laps.map((lap) => (
          <tr
            key={lap.lap_number}
            className={`${lap.counts ? "" : "excluded"} ${lap.lap_number === bestLap ? "best" : ""}`}
          >
            <td className="left">{lap.lap_number}</td>
            <td className="time">{formatLapTime(lap.lap_time_ms)}</td>
            <td>{formatSector(lap.sector1_ms)}</td>
            <td>{formatSector(lap.sector2_ms)}</td>
            <td>{formatSector(lap.sector3_ms)}</td>
            <td className="left">
              <span className={`compound ${lap.tyre_visual_compound_name}`}>
                {lap.tyre_visual_compound_name}
              </span>
            </td>
            <td>{lap.tyre_age_laps}</td>
            <td>
              {lap.tyre_wear_fl !== null
                ? `${lap.tyre_wear_fl.toFixed(1)} / ${lap.tyre_wear_fr?.toFixed(1)}`
                : "—"}
            </td>
            <td>
              {lap.tyre_wear_rl !== null
                ? `${lap.tyre_wear_rl.toFixed(1)} / ${lap.tyre_wear_rr?.toFixed(1)}`
                : "—"}
            </td>
            <td>{lap.car_position || "—"}</td>
            <td className="left">
              {lap.counts ? (
                "Yes"
              ) : (
                <span className="reason">
                  {EXCLUSION_LABELS[lap.exclusion_reason ?? ""] ?? lap.exclusion_reason}
                </span>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function SessionDetail({ uid, onBack }: { uid: string; onBack: () => void }) {
  const [session, setSession] = useState<Detail | null>(null);
  const [laps, setLaps] = useState<LapRow[]>([]);
  const [stints, setStints] = useState<StintRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.session(uid), api.laps(uid), api.stints(uid)])
      .then(([s, l, st]) => {
        setSession(s);
        setLaps(l.items);
        setStints(st.items);
        setError(null);
      })
      .catch((e: Error) => setError(e.message));
  }, [uid]);

  if (error) return <div className="error">{error}</div>;
  if (!session) return <div className="empty">Loading…</div>;

  return (
    <>
      <button className="back" onClick={onBack}>
        ← All sessions
      </button>

      <div className="detail-head">
        <h2>{session.track_name}</h2>
        <span className="tag race">{session.session_type_name}</span>
        {session.started_late ? <span className="tag warn">started late</span> : null}
        {session.incomplete ? <span className="tag warn">incomplete recording</span> : null}
      </div>
      <div className="detail-sub">
        {formatDate(session.started_at)} · {formatDuration(session.duration_s)} ·{" "}
        {session.num_laps} laps, {session.num_counting_laps} counting · best{" "}
        {formatLapTime(session.best_lap_ms)}
      </div>

      <ContextPanel session={session} />

      {stints.length > 0 ? (
        <>
          <h3 className="section-title">Stints</h3>
          <div className="stints">
            {stints.map((s) => (
              <div className="stint" key={s.stint_index}>
                <span className={`compound ${s.tyre_visual_compound_name}`}>
                  {s.tyre_visual_compound_name}
                </span>
                <div className="laps">
                  Laps {s.start_lap}–{s.end_lap ?? "…"} · {s.num_laps} lap
                  {s.num_laps === 1 ? "" : "s"}
                </div>
              </div>
            ))}
          </div>
        </>
      ) : null}

      <h3 className="section-title">Laps</h3>
      <LapTable laps={laps} bestLap={session.best_lap_number} />
    </>
  );
}
