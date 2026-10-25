import type { PaceLap, PaceStint } from "../api";

/** Pure helpers for the session-pace chart (kept free of React/uPlot for easy reasoning). */

/** Padding either side of the counting-lap range in "Valid laps" mode, in seconds. */
export const VALID_PAD_S = 0.3;

const seconds = (ms: number | null): number | null => (ms === null || ms <= 0 ? null : ms / 1000);

/** Stint a lap belongs to: its own stint_index, else the stint whose lap span contains it. */
export function stintKey(lap: PaceLap, stints: PaceStint[]): number {
  if (lap.stint_index !== null && lap.stint_index !== undefined) return lap.stint_index;
  const hit = stints.find((s) => lap.lap_number >= s.start_lap && (s.end_lap === null || lap.lap_number <= s.end_lap));
  return hit ? hit.stint_index : -1;
}

/**
 * Rolling mean of lap time (seconds), aligned with `laps` (which must be sorted by lap).
 *
 * - Only counting laps contribute and only counting laps get a value.
 * - The window never crosses a stint boundary: it is the lap plus the previous
 *   (window-1) counting laps of the SAME stint.
 * - A value exists only once `window` counting laps are available in the stint.
 * Everything else is null.
 */
export function movingAverage(laps: PaceLap[], window: number, stints: PaceStint[] = []): (number | null)[] {
  const out: (number | null)[] = laps.map(() => null);
  if (window < 1) return out;
  const history = new Map<number, number[]>(); // stint -> counting lap times so far
  laps.forEach((lap, i) => {
    const t = lap.counts ? seconds(lap.lap_time_ms) : null;
    if (t === null) return;
    const key = stintKey(lap, stints);
    const times = history.get(key) ?? [];
    times.push(t);
    history.set(key, times);
    if (times.length >= window) {
      let sum = 0;
      for (let k = times.length - window; k < times.length; k++) sum += times[k];
      out[i] = sum / window;
    }
  });
  return out;
}

/**
 * Split the moving average into one array per stint (null elsewhere), so each stint
 * can be its own line series and nothing is drawn across a pit stop.
 * Stints that never reach a full window are omitted.
 */
export function averageSegments(
  laps: PaceLap[],
  avg: (number | null)[],
  stints: PaceStint[],
): (number | null)[][] {
  const byStint = new Map<number, (number | null)[]>();
  laps.forEach((lap, i) => {
    if (avg[i] === null) return;
    const key = stintKey(lap, stints);
    let arr = byStint.get(key);
    if (!arr) {
      arr = laps.map(() => null);
      byStint.set(key, arr);
    }
    arr[i] = avg[i];
  });
  return [...byStint.entries()].sort((a, b) => a[0] - b[0]).map(([, arr]) => arr);
}

/** [min, max] seconds of the laps that count, padded; falls back to every timed lap. */
export function validRange(laps: PaceLap[]): [number, number] | null {
  const pick = (only: boolean) =>
    laps
      .filter((l) => (only ? l.counts : true))
      .map((l) => seconds(l.lap_time_ms))
      .filter((v): v is number => v !== null);
  let times = pick(true);
  if (times.length === 0) times = pick(false);
  if (times.length === 0) return null;
  return [Math.min(...times) - VALID_PAD_S, Math.max(...times) + VALID_PAD_S];
}

/** Unpadded [min, max] seconds of every lap with a time. */
export function allRange(laps: PaceLap[]): [number, number] | null {
  const times = laps.map((l) => seconds(l.lap_time_ms)).filter((v): v is number => v !== null);
  if (times.length === 0) return null;
  return [Math.min(...times), Math.max(...times)];
}

/** Parse "1:20.5" (m:ss.s) or "80.5" (seconds). Returns seconds, or null if invalid. */
export function parseLapInput(text: string): number | null {
  const s = text.trim().replace(",", ".");
  let m = /^(\d+):(\d{1,2}(?:\.\d+)?)$/.exec(s);
  if (m) {
    const sec = Number(m[2]);
    return sec < 60 ? Number(m[1]) * 60 + sec : null;
  }
  m = /^(\d+(?:\.\d+)?)$/.exec(s);
  if (m) return Number(m[1]);
  return null;
}

/** Seconds as m:ss.s text for the manual inputs. */
export function formatRangeInput(sec: number): string {
  const m = Math.floor(sec / 60);
  const rest = (sec - m * 60).toFixed(1).padStart(4, "0");
  // toFixed can round 59.96 up to "60.0"
  if (rest.startsWith("60")) return `${m + 1}:00.0`;
  return m > 0 ? `${m}:${rest}` : rest;
}
