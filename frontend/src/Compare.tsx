import { useEffect, useMemo, useState } from "react";
import {
  api,
  EXCLUSION_LABELS,
  formatDate,
  formatLapTime,
  type CompareResult,
  type ExcursionRow,
  type LapContext,
  type LapTrace,
  type PaceData,
  type SessionDetail,
  type TrackLapRow,
} from "./api";
import { PaceChart } from "./charts/PaceChart";
import { GapChart } from "./charts/GapChart";
import { TrackMap } from "./charts/TrackMap";
import { TraceCharts } from "./charts/TraceCharts";
import { GGDiagram } from "./charts/GGDiagram";

const lapRef = (uid: string, lap: number) => `${uid}:${lap}`;

function reasonText(reason: string | null): string {
  return EXCLUSION_LABELS[reason ?? ""] ?? reason ?? "does not count";
}

/** "date · session type · lap N · time (or the reason it doesn't count)". */
function lapLabel(row: TrackLapRow): string {
  let time: string;
  if (row.lap_time_ms === null) time = `no time (${reasonText(row.exclusion_reason ?? "incomplete")})`;
  else if (row.counts) time = formatLapTime(row.lap_time_ms);
  else time = `${formatLapTime(row.lap_time_ms)} (not counting: ${reasonText(row.exclusion_reason)})`;
  const trace = row.has_trace ? "" : " · no trace";
  return `${formatDate(row.started_at)} · ${row.session_type_name} · lap ${row.lap_number} · ${time}${trace}`;
}

// Fields of the context payload, in display order. `differs` uses these same names.
const CONTEXT_FIELDS: { key: keyof LapContext; label: string; format?: (v: LapContext[keyof LapContext]) => string }[] = [
  { key: "assists_summary", label: "Assists" },
  { key: "tyre", label: "Tyre" },
  { key: "tyre_age_laps", label: "Tyre age", format: (v) => (v === null ? "—" : `${v} lap${v === 1 ? "" : "s"}`) },
  { key: "fuel_in_tank_start", label: "Fuel at start", format: (v) => (typeof v === "number" ? `${v.toFixed(1)}` : "—") },
  { key: "weather_name", label: "Weather" },
  { key: "track_temp_c", label: "Track temp", format: (v) => (v === null ? "—" : `${v}°C`) },
  { key: "ai_difficulty", label: "AI difficulty" },
];

function ContextCompare({ result }: { result: CompareResult }) {
  const { context, lap, reference } = result;
  const differs = new Set(context.differs);
  const show = (field: (typeof CONTEXT_FIELDS)[number], ctx: LapContext) => {
    const v = ctx[field.key];
    if (field.format) return field.format(v);
    return v === null || v === undefined || v === "" ? "—" : String(v);
  };

  const heading = (trace: LapTrace, name: string) => (
    <div className="ctx-col-head">
      {name} · lap {trace.lap_number} · {formatLapTime(trace.lap_time_ms)}
      {trace.counts ? null : (
        <span className="tag warn" title={reasonText(trace.exclusion_reason)}>
          not counting: {reasonText(trace.exclusion_reason)}
        </span>
      )}
    </div>
  );

  return (
    <div className="compare-context">
      <div className="ctx-grid">
        <div />
        {heading(lap, "Compared")}
        {heading(reference, "Reference")}
        {CONTEXT_FIELDS.map((f) => (
          <div className={`ctx-row${differs.has(f.key) ? " differs" : ""}`} key={f.key}>
            <div className="k">{f.label}</div>
            <div className="v">{show(f, context.lap)}</div>
            <div className="v">{show(f, context.reference)}</div>
          </div>
        ))}
      </div>
      {differs.size > 0 ? (
        <div className="chart-caption">
          Highlighted rows differ between the two laps, so the comparison is not like for like.
        </div>
      ) : (
        <div className="chart-caption">The two laps were driven under the same conditions.</div>
      )}
    </div>
  );
}

// Excursions are per session and static while the page is open, so fetch each once.
const excursionCache = new Map<string, Promise<ExcursionRow[]>>();

function loadExcursions(uid: string): Promise<ExcursionRow[]> {
  let p = excursionCache.get(uid);
  if (!p) {
    p = api.excursions(uid).then((r) => r.items);
    // A failure must not be cached: the driver may run ingest and come back.
    p.catch(() => excursionCache.delete(uid));
    excursionCache.set(uid, p);
  }
  return p;
}

/** The compared lap's off-track excursions, or the server's message when it has none to give. */
function useExcursions(uid: string, lapNumber: number) {
  const [items, setItems] = useState<ExcursionRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    setItems(null);
    setError(null);
    loadExcursions(uid)
      .then((all) => !cancelled && setItems(all.filter((e) => e.lap_number === lapNumber)))
      .catch((e: Error) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [uid, lapNumber]);
  return { items, error };
}

function ExcursionList({
  lap,
  items,
  error,
}: {
  lap: LapTrace;
  items: ExcursionRow[] | null;
  error: string | null;
}) {
  const wheelNames = (wheels: string) =>
    wheels
      .split(",")
      .map((w) => w.trim())
      .filter((w) => w !== "")
      .map((w) => w.toUpperCase())
      .join(" + ");

  return (
    <div className="excursion-list">
      <div className="chart-title">Track limits, lap {lap.lap_number}</div>
      {error ? (
        <div className="chart-caption">{error}</div>
      ) : items === null ? (
        <div className="chart-caption">Loading…</div>
      ) : items.length === 0 ? (
        <div className="chart-caption">No wheel left the track on this lap.</div>
      ) : (
        <table>
          <thead>
            <tr>
              <th className="left">At</th>
              <th>Length</th>
              <th className="left">Wheels</th>
              <th className="left">Surface</th>
            </tr>
          </thead>
          <tbody>
            {items.map((e) => (
              <tr key={`${e.start_m}-${e.session_time_s}`}>
                <td className="left">{Math.round(e.start_m)} m</td>
                <td>{Math.round(e.length_m)} m</td>
                <td className="left" title="FL front-left, FR front-right, RL rear-left, RR rear-right">
                  {wheelNames(e.wheels)}
                </td>
                <td className="left">{e.surface}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

/** Holds the cursor distance locally so moving the pointer re-renders only the map. */
function Analysis({ result }: { result: CompareResult }) {
  const [cursor, setCursor] = useState<number | null>(null);
  const excursions = useExcursions(result.lap.session_uid, result.lap.lap_number);
  const warnings = [
    result.lap.counts ? null : `Compared lap ${result.lap.lap_number} does not count (${reasonText(result.lap.exclusion_reason)}).`,
    result.reference.counts
      ? null
      : `Reference lap ${result.reference.lap_number} does not count (${reasonText(result.reference.exclusion_reason)}).`,
  ].filter((w): w is string => w !== null);

  return (
    <>
      {warnings.length > 0 ? (
        <div className="compare-warning">
          <span className="tag warn">not a valid timed lap</span> {warnings.join(" ")}
        </div>
      ) : null}

      <ContextCompare result={result} />

      <div className="compare-top">
        <GapChart gap={result.gap} lap={result.lap} reference={result.reference} />
        <TrackMap
          trace={result.lap}
          reference={result.reference}
          cursorDistance={cursor}
          excursions={excursions.items ?? undefined}
        />
      </div>

      <div className="compare-top">
        <GGDiagram lap={result.lap} reference={result.reference} cursorDistance={cursor} />
        <ExcursionList lap={result.lap} items={excursions.items} error={excursions.error} />
      </div>

      <TraceCharts lap={result.lap} reference={result.reference} onCursor={setCursor} />
    </>
  );
}

export function Compare({ sessionUid, onBack }: { sessionUid: string; onBack: () => void }) {
  const [session, setSession] = useState<SessionDetail | null>(null);
  const [pace, setPace] = useState<PaceData | null>(null);
  const [trackLaps, setTrackLaps] = useState<TrackLapRow[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [lapSel, setLapSel] = useState("");
  const [refSel, setRefSel] = useState(""); // "" = let the server pick the best counting lap
  const [result, setResult] = useState<CompareResult | null>(null);
  const [compareError, setCompareError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  // Initial load: session, pace chart data, and every lap at this circuit.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const s = await api.session(sessionUid);
        const [p, l] = await Promise.all([api.pace(sessionUid), api.lapsAtTrack(s.track_id)]);
        if (cancelled) return;
        setSession(s);
        setPace(p);
        setTrackLaps(l.items);
        setLoadError(null);

        // Default: the FASTEST lap of this session that has a time and a trace and is
        // not the session's best lap (the best lap is what the reference defaults to).
        // Falls back to the best lap itself when nothing else qualifies.
        const mine = l.items.filter(
          (r) => r.session_uid === sessionUid && r.has_trace && r.lap_time_ms !== null,
        );
        const fastest = (rows: TrackLapRow[]) =>
          rows.reduce<TrackLapRow | undefined>(
            (best, r) =>
              best === undefined || (r.lap_time_ms ?? Infinity) < (best.lap_time_ms ?? Infinity)
                ? r
                : best,
            undefined,
          );
        const pick =
          fastest(mine.filter((r) => r.lap_number !== s.best_lap_number)) ??
          mine.find((r) => r.lap_number === s.best_lap_number);
        if (pick) setLapSel(lapRef(pick.session_uid, pick.lap_number));
      } catch (e) {
        if (!cancelled) setLoadError((e as Error).message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionUid]);

  // Fetch the comparison whenever either selection changes.
  useEffect(() => {
    if (!lapSel) {
      setResult(null);
      return;
    }
    let cancelled = false;
    setBusy(true);
    setCompareError(null);
    api
      .compare(lapSel, refSel || undefined)
      .then((r) => {
        if (cancelled) return;
        setResult(r);
      })
      .catch((e: Error) => {
        if (cancelled) return;
        setResult(null);
        setCompareError(e.message); // verbatim: the server explains why
      })
      .finally(() => !cancelled && setBusy(false));
    return () => {
      cancelled = true;
    };
  }, [lapSel, refSel]);

  // Current session first, then newest sessions, laps in order.
  const sortedLaps = useMemo(
    () =>
      [...trackLaps].sort((a, b) => {
        const mineA = a.session_uid === sessionUid ? 0 : 1;
        const mineB = b.session_uid === sessionUid ? 0 : 1;
        if (mineA !== mineB) return mineA - mineB;
        if (a.started_at !== b.started_at) return a.started_at < b.started_at ? 1 : -1;
        if (a.session_uid !== b.session_uid) return a.session_uid < b.session_uid ? 1 : -1;
        return a.lap_number - b.lap_number;
      }),
    [trackLaps, sessionUid],
  );

  const onSelectPaceLap = (lapNumber: number) => {
    const row = trackLaps.find((r) => r.session_uid === sessionUid && r.lap_number === lapNumber);
    if (!row) return;
    if (!row.has_trace) {
      setNote(`Lap ${lapNumber} has no trace, so it cannot be compared.`);
      return;
    }
    setNote(null);
    setLapSel(lapRef(row.session_uid, row.lap_number));
  };

  if (loadError) {
    return (
      <>
        <button className="back" onClick={onBack}>
          ← Back to session
        </button>
        <div className="error">{loadError}</div>
      </>
    );
  }
  if (!session || !pace) return <div className="empty">Loading…</div>;

  const selectedLapNumber =
    lapSel.startsWith(`${sessionUid}:`) ? Number(lapSel.slice(sessionUid.length + 1)) : null;

  return (
    <>
      <button className="back" onClick={onBack}>
        ← Back to session
      </button>
      <div className="detail-head">
        <h2>Compare laps</h2>
        <span className="tag race">{session.track_name}</span>
      </div>
      <div className="detail-sub">
        {formatDate(session.started_at)} · {session.session_type_name}
      </div>

      <PaceChart pace={pace} selectedLap={selectedLapNumber} onSelectLap={onSelectPaceLap} />
      {note ? <div className="chart-caption">{note}</div> : null}

      <div className="pickers">
        <label>
          <span className="k">Lap</span>
          <select value={lapSel} onChange={(e) => setLapSel(e.target.value)}>
            {lapSel === "" ? <option value="">Choose a lap…</option> : null}
            {sortedLaps.map((r) => (
              <option
                key={lapRef(r.session_uid, r.lap_number)}
                value={lapRef(r.session_uid, r.lap_number)}
                disabled={!r.has_trace}
              >
                {lapLabel(r)}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="k">Reference</span>
          <select value={refSel} onChange={(e) => setRefSel(e.target.value)}>
            <option value="">Best counting lap of the compared lap’s session (default)</option>
            {sortedLaps.map((r) => (
              <option
                key={lapRef(r.session_uid, r.lap_number)}
                value={lapRef(r.session_uid, r.lap_number)}
                // A reference needs a complete time (FR-019) and a trace.
                disabled={!r.has_trace || r.lap_time_ms === null}
              >
                {lapLabel(r)}
              </option>
            ))}
          </select>
        </label>
      </div>

      {compareError ? <div className="error">{compareError}</div> : null}
      {busy && !result ? <div className="empty">Loading traces…</div> : null}
      {!lapSel && !compareError ? (
        <div className="empty">No lap with a recorded trace is available to compare.</div>
      ) : null}
      {result ? (
        <div className={busy ? "compare-body loading" : "compare-body"}>
          <Analysis result={result} />
        </div>
      ) : null}
    </>
  );
}
