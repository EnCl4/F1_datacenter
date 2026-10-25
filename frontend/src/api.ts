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

export type Wheel = "fl" | "fr" | "rl" | "rr";
export const WHEELS: readonly Wheel[] = ["fl", "fr", "rl", "rr"];
export const WHEEL_NAMES: Record<Wheel, string> = {
  fl: "Front-left",
  fr: "Front-right",
  rl: "Rear-left",
  rr: "Rear-right",
};

type Column = (number | null)[];

/**
 * Channels added by feature 003. Optional: a session ingested before they existed
 * returns traces without them, and the charts then say so instead of drawing nothing.
 */
export type ExtraTraceChannels = {
  [W in Wheel as `tyre_surface_${W}` | `tyre_inner_${W}` | `brake_${W}` | `pressure_${W}`]?: Column;
} & {
  gap_ahead_ms?: Column;
  /** 1 while any wheel is off the track, else 0 (step-held). */
  off_track?: Column;
};

export type ChannelKey = keyof TraceChannels | keyof ExtraTraceChannels;

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
  channels: TraceChannels & ExtraTraceChannels;
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

// --- feature 003: car and race data (contracts/http-api.md, data-model.md) ----------

type PerWheel<P extends string> = { [W in Wheel as `${P}_${W}`]: number | null };

/** One row per lap of lap_car.parquet. Wheel columns are always suffixed, never positional. */
export type LapCarRow = PerWheel<"tyre_surface_avg"> &
  PerWheel<"tyre_surface_max"> &
  PerWheel<"tyre_inner_avg"> &
  PerWheel<"tyre_inner_max"> &
  PerWheel<"brake_avg"> &
  PerWheel<"brake_max"> &
  PerWheel<"pressure_avg"> & {
    lap_number: number;
    engine_temp_max: number | null;
    tyre_change_in_lap: boolean;
    ers_start_mj: number | null;
    ers_end_mj: number | null;
    ers_deployed_mj: number | null;
    ers_harvested_mj: number | null;
    /** harvested - deployed; negative = deficit. */
    ers_balance_mj: number | null;
    ers_modes: string | null;
    fuel_start_kg: number | null;
    fuel_end_kg: number | null;
    fuel_used_kg: number | null;
    fuel_mix: string | null;
    brake_bias: string | null;
    settings_changed: boolean;
    damage_front_left_wing: number | null;
    damage_front_right_wing: number | null;
    damage_rear_wing: number | null;
    damage_floor: number | null;
    damage_diffuser: number | null;
    damage_sidepod: number | null;
    damage_gearbox: number | null;
    damage_engine: number | null;
    damage_increased: boolean;
    excursions: number | null;
    excursion_m: number | null;
    drs_pct: number | null;
    position_at_line: number | null;
    /** Null when P1. */
    gap_ahead_ms_at_line: number | null;
    corner_warnings: number | null;
    penalties_s: number | null;
  };

export interface ExcursionRow {
  lap_number: number;
  start_m: number;
  length_m: number;
  /** e.g. "fl,fr" */
  wheels: string;
  /** e.g. "grass" */
  surface: string;
  session_time_s: number;
}

export interface FieldCar {
  car_idx: number;
  name: string;
  team_id: number;
  race_number: number;
  ai_controlled: boolean;
  is_player: boolean;
  best_lap_ms: number | null;
  best_lap_number: number | null;
  num_laps: number;
  finish_position: number | null;
  result_status: string;
  /** e.g. "Soft 1-4 · Soft 5-5" */
  stints: string;
}

export interface FieldLap {
  car_idx: number;
  lap_number: number;
  lap_time_ms: number | null;
  valid: boolean;
}

export interface FieldData {
  cars: FieldCar[];
  player_rank: number | null;
  laps: FieldLap[];
}

export interface ConditionRow {
  session_time_s: number;
  lap_number: number;
  weather: string;
  track_temp_c: number;
  air_temp_c: number;
}

export interface EventRow {
  session_time_s: number;
  lap_number: number;
  code: string;
  vehicle_idx: number;
  other_vehicle_idx: number;
  value: number | null;
  involves_player: boolean;
  description: string;
}

export interface TimelineData {
  conditions: ConditionRow[];
  events: EventRow[];
}

export interface TyreSetRow {
  set_index: number;
  actual_compound: string;
  visual_compound: string;
  wear_pct: number;
  available: boolean;
  fitted: boolean;
  /** The game's estimate against the fitted set; negative = faster. */
  lap_delta_ms: number | null;
  life_span: number | null;
  usable_life: number | null;
}

export interface DeleteResult {
  deleted: boolean;
  session_uid: string;
  removed: string[];
  left_behind: string[];
}

/**
 * An API error. `message` is the server's own text, verbatim (it is written for the
 * user: which circuits differ, why a 409 happened, to run ingest again, ...). `code`
 * is the machine code, e.g. data_unavailable, busy, partial_delete.
 */
export class ApiError extends Error {
  readonly code: string | null;
  readonly status: number;
  readonly removed: string[];
  readonly leftBehind: string[];

  constructor(
    message: string,
    status: number,
    code: string | null,
    removed: string[] = [],
    leftBehind: string[] = [],
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.removed = removed;
    this.leftBehind = leftBehind;
  }
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : [];
}

interface ErrorBody {
  error?: { code?: string; message?: string; removed?: unknown; left_behind?: unknown };
  removed?: unknown;
  left_behind?: unknown;
}

/**
 * Errors arrive as {error:{code,message}}. The message is already written for the
 * user (e.g. which two circuits differ, or why a trace is missing), so it is surfaced
 * verbatim rather than being reworded here.
 *
 * partial_delete also lists `removed` and `left_behind`; the contract does not say
 * whether they sit beside or inside `error`, so both places are read.
 */
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, init);
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as ErrorBody | null;
    throw new ApiError(
      body?.error?.message ?? `request failed: ${response.status}`,
      response.status,
      body?.error?.code ?? null,
      stringList(body?.error?.removed ?? body?.removed),
      stringList(body?.error?.left_behind ?? body?.left_behind),
    );
  }
  return response.json() as Promise<T>;
}

const get = <T,>(path: string): Promise<T> => request<T>(path);

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

  // Feature 003. A session ingested before 1.2.0 answers 409 data_unavailable.
  car: (uid: string) => get<{ laps: LapCarRow[] }>(`/sessions/${uid}/car`),
  excursions: (uid: string) => get<{ items: ExcursionRow[] }>(`/sessions/${uid}/excursions`),
  field: (uid: string) => get<FieldData>(`/sessions/${uid}/field`),
  timeline: (uid: string) => get<TimelineData>(`/sessions/${uid}/timeline`),
  tyreSets: (uid: string) => get<{ items: TyreSetRow[] }>(`/sessions/${uid}/tyre-sets`),
};

/**
 * The only write in the app: permanently deletes a session AND its original recording.
 * `confirm` is the circuit name as the driver typed it; the server verifies it itself
 * (case-insensitive, trimmed) and refuses otherwise.
 */
export function deleteSession(uid: string, confirm: string): Promise<DeleteResult> {
  return request<DeleteResult>(
    `/sessions/${encodeURIComponent(uid)}?confirm=${encodeURIComponent(confirm)}`,
    { method: "DELETE" },
  );
}

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
