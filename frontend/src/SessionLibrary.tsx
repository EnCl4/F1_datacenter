import { useEffect, useMemo, useState } from "react";
import {
  api,
  formatDate,
  formatDuration,
  formatLapTime,
  type SessionRow,
  type TrackRow,
} from "./api";

const CATEGORIES = [
  ["", "All types"],
  ["race", "Race"],
  ["qualifying", "Qualifying"],
  ["practice", "Practice"],
  ["time_trial", "Time trial"],
] as const;

/**
 * FR-022 and constitution principle VI: never show a lap time without the context needed
 * to judge whether it is comparable. That is why every card carries the assists, weather
 * and difficulty alongside the best lap, rather than the time alone.
 */
function SessionCard({ session, onOpen }: { session: SessionRow; onOpen: () => void }) {
  return (
    <button className="card" onClick={onOpen}>
      <div className="title">
        {session.track_name}
        <span className={`tag ${session.session_category === "race" ? "race" : ""}`}>
          {session.session_type_name}
        </span>
        {session.started_late ? <span className="tag warn">started late</span> : null}
        {!session.ended_naturally ? <span className="tag warn">{session.end_reason}</span> : null}
        {session.loss_pct > 1 ? (
          <span className="tag bad">{session.loss_pct.toFixed(1)}% lost</span>
        ) : null}
        {session.starred ? <span className="tag">kept</span> : null}
      </div>

      <div className="best">
        <div className="time">{formatLapTime(session.best_lap_ms)}</div>
        <div className="label">
          {session.best_lap_ms ? `best · lap ${session.best_lap_number}` : "no counting lap"}
        </div>
      </div>

      <div className="meta">
        {formatDate(session.started_at)} · {formatDuration(session.duration_s)} ·{" "}
        {session.num_laps} lap{session.num_laps === 1 ? "" : "s"} ({session.num_counting_laps}{" "}
        counting)
      </div>

      <div className="ctx">
        {session.weather_name} · track {session.track_temp_c}°C · air {session.air_temp_c}°C · AI{" "}
        {session.ai_difficulty} · {session.assists_summary}
      </div>
    </button>
  );
}

export function SessionLibrary({
  onOpen,
  onTotal,
}: {
  onOpen: (uid: string) => void;
  onTotal: (total: number) => void;
}) {
  const [sessions, setSessions] = useState<SessionRow[]>([]);
  const [tracks, setTracks] = useState<TrackRow[]>([]);
  const [track, setTrack] = useState("");
  const [category, setCategory] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const params = useMemo(() => {
    const p: Record<string, string> = { limit: "200" };
    if (track) p.track_id = track;
    if (category) p.session_category = category;
    if (from) p.from = from;
    if (to) p.to = to;
    return p;
  }, [track, category, from, to]);

  useEffect(() => {
    api.tracks().then((r) => setTracks(r.items)).catch(() => setTracks([]));
  }, []);

  useEffect(() => {
    setLoading(true);
    api
      .sessions(params)
      .then((r) => {
        setSessions(r.items);
        onTotal(r.total);
        setError(null);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [params, onTotal]);

  const filtered = track || category || from || to;

  return (
    <>
      <div className="filters">
        <select value={track} onChange={(e) => setTrack(e.target.value)}>
          <option value="">All circuits</option>
          {tracks.map((t) => (
            <option key={t.track_id} value={String(t.track_id)}>
              {t.track_name} ({t.session_count})
            </option>
          ))}
        </select>

        <select value={category} onChange={(e) => setCategory(e.target.value)}>
          {CATEGORIES.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>

        <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} title="From" />
        <input type="date" value={to} onChange={(e) => setTo(e.target.value)} title="To" />

        {filtered ? (
          <button
            className="clear"
            onClick={() => {
              setTrack("");
              setCategory("");
              setFrom("");
              setTo("");
            }}
          >
            Clear filters
          </button>
        ) : null}
      </div>

      {error ? <div className="error">{error}</div> : null}

      {!error && !loading && sessions.length === 0 ? (
        <div className="empty">
          {filtered
            ? "No sessions match these filters."
            : "No sessions recorded yet. Start the recorder, then drive."}
        </div>
      ) : null}

      <div className="sessions">
        {sessions.map((s) => (
          <SessionCard
            key={s.session_uid}
            session={s}
            onOpen={() => onOpen(s.session_uid)}
          />
        ))}
      </div>
    </>
  );
}
