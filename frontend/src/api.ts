/** Typed client for the read-only API. Mirrors contracts/http-api.md. */

export interface RecorderState {
  recording: boolean;
  state: string;
  stale: boolean;
  loss_pct: number;
  free_disk_gb: number | null;
  message: string | null;
  session: {
    uid: string;
    track_id: number;
    session_type: number;
    current_lap: number;
    started_late: boolean;
  } | null;
}

export interface SessionRow {
  session_uid: string;
  started_at: string;
  track_id: number;
  track_name: string;
  session_type_name: string;
  session_category: string;
  duration_s: number;
  num_laps: number;
  num_counting_laps: number;
  best_lap_ms: number | null;
  best_lap_number: number | null;
  weather_name: string;
  air_temp_c: number;
  track_temp_c: number;
  ai_difficulty: number;
  assists_summary: string;
  ended_naturally: boolean;
  end_reason: string;
  started_late: boolean;
  loss_pct: number;
  incomplete: boolean;
  starred: boolean;
}

export interface SessionDetail extends SessionRow {
  track_length_m: number;
  total_laps: number;
  assists: Record<string, number>;
  conditions: { weather_name: string; air_temp_c: number; track_temp_c: number };
}

export interface LapRow {
  lap_number: number;
  stint_index: number | null;
  lap_time_ms: number | null;
  sector1_ms: number | null;
  sector2_ms: number | null;
  sector3_ms: number | null;
  valid: boolean;
  counts: boolean;
  exclusion_reason: string | null;
  is_in_lap: boolean;
  is_out_lap: boolean;
  pit_status: number;
  tyre_visual_compound_name: string;
  tyre_age_laps: number;
  tyre_wear_rl: number | null;
  tyre_wear_rr: number | null;
  tyre_wear_fl: number | null;
  tyre_wear_fr: number | null;
  car_position: number;
  penalties_s: number;
  corner_cutting_warnings: number;
}

export interface StintRow {
  stint_index: number;
  start_lap: number;
  end_lap: number | null;
  tyre_visual_compound_name: string;
  tyre_actual_compound_name: string;
  num_laps: number;
}

export interface TrackRow {
  track_id: number;
  track_name: string;
  session_count: number;
}

/** One column per channel; null marks a recording gap (never interpolated). */
export interface TraceChannels {
  distance_m: number[];
  time_ms: (number | null)[];
  speed_kph: (number | null)[];
  throttle: (number | null)[];
  brake: (number | null)[];
  steer: (number | null)[];
  gear: (number | null)[];
  rpm: (number | null)[];
  drs: (number | null)[];
  g_lat: (number | null)[];
  g_lon: (number | null)[];
  x: (number | null)[];
  z: (number | null)[];
}

export type ChannelKey = keyof TraceChannels;

export interface LapTrace {
  session_uid: string;
  lap_number: number;
  track_id: number;
  track_length_m: number;
  lap_time_ms: number | null;
  counts: boolean;
  exclusion_reason: string | null;
  /** Distances where sectors 2 and 3 begin. */
  sectors_m: number[];
  channels: TraceChannels;
}

export interface GapSeries {
  distance_m: number[];
  /** Positive = the compared lap is behind the reference at that distance. */
  gap_ms: (number | null)[];
}

export interface LapContext {
  assists_summary: string | null;
  tyre: string | null;
  tyre_age_laps: number | null;
  weather_name: string | null;
  track_temp_c: number | null;
  ai_difficulty: number | null;
  fuel_in_tank_start: number | null;
}

export interface CompareContext {
  lap: LapContext;
  reference: LapContext;
  /** Names of the LapContext fields whose values differ between the two laps. */
  differs: string[];
}

export interface CompareResult {
  lap: LapTrace;
  reference: LapTrace;
  gap: GapSeries;
  context: CompareContext;
}

export interface PaceLap {
  lap_number: number;
  lap_time_ms: number | null;
  counts: boolean;
  exclusion_reason: string | null;
  stint_index: number | null;
  tyre_visual_compound_name: string;
}

export interface PaceStint {
  stint_index: number;
  start_lap: number;
  end_lap: number | null;
  tyre_visual_compound_name: string;
}

export interface PaceData {
  laps: PaceLap[];
  stints: PaceStint[];
}

export interface TrackLapRow {
  session_uid: string;
  started_at: string;
  session_type_name: string;
  lap_number: number;
  lap_time_ms: number | null;
  counts: boolean;
  exclusion_reason: string | null;
  has_trace: boolean;
}

/**
 * Errors arrive as {error:{code,message}}. The message is already written for the
 * user (e.g. which two circuits differ, or why a trace is missing), so it is surfaced
 * verbatim rather than being reworded here.
 */
async function get<T>(path: string): Promise<T> {
  const response = await fetch(`/api${path}`);
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      error?: { code?: string; message?: string };
    } | null;
    throw new Error(body?.error?.message ?? `request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  status: () => get<RecorderState>("/status"),
  tracks: () => get<{ items: TrackRow[] }>("/tracks"),
  sessions: (params: Record<string, string>) => {
    const query = new URLSearchParams(params).toString();
    return get<{ total: number; items: SessionRow[] }>(`/sessions${query ? `?${query}` : ""}`);
  },
  session: (uid: string) => get<SessionDetail>(`/sessions/${uid}`),
  laps: (uid: string) => get<{ items: LapRow[] }>(`/sessions/${uid}/laps`),
  stints: (uid: string) => get<{ items: StintRow[] }>(`/sessions/${uid}/stints`),
  trace: (uid: string, lap: number) => get<LapTrace>(`/sessions/${uid}/laps/${lap}/trace`),
  /** Refs use the "sessionUid:lapNumber" form. Omit the reference for the session's best counting lap. */
  compare: (lapRef: string, referenceRef?: string) => {
    const params = new URLSearchParams({ lap: lapRef });
    if (referenceRef) params.set("reference", referenceRef);
    return get<CompareResult>(`/compare?${params.toString()}`);
  },
  pace: (uid: string) => get<PaceData>(`/sessions/${uid}/pace`),
  lapsAtTrack: (trackId: number) =>
    get<{ items: TrackLapRow[] }>(`/laps?track_id=${encodeURIComponent(String(trackId))}`),
};

/** Lap times are read constantly and compared by eye, so format them consistently. */
export function formatLapTime(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || ms <= 0) return "—";
  const minutes = Math.floor(ms / 60000);
  const seconds = ((ms % 60000) / 1000).toFixed(3).padStart(6, "0");
  return minutes > 0 ? `${minutes}:${seconds}` : seconds;
}

export function formatSector(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || ms <= 0) return "—";
  return (ms / 1000).toFixed(3);
}

export function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}m ${s.toString().padStart(2, "0")}s`;
}

export function formatDate(iso: string): string {
  if (!iso) return "unknown";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Human label for why a lap does not count. Shown verbatim from the API's reason code. */
export const EXCLUSION_LABELS: Record<string, string> = {
  invalidated: "Invalidated",
  in_lap: "In lap",
  out_lap: "Out lap",
  pit: "Pit lap",
  safety_car: "Safety car",
  first_lap: "First lap",
  incomplete: "Incomplete",
};
