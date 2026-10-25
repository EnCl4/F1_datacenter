import type { LapTrace } from "../api";

/** Index of the sample whose distance is closest to `d` (distances are ascending). */
export function nearestIndex(distances: number[], d: number): number {
  let lo = 0;
  let hi = distances.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (distances[mid] < d) lo = mid + 1;
    else hi = mid;
  }
  if (lo > 0 && Math.abs(distances[lo - 1] - d) <= Math.abs(distances[lo] - d)) return lo - 1;
  return lo;
}

/** A stretch of the lap, in metres from the line. */
export interface DistanceRun {
  from: number;
  to: number;
}

/** Contiguous stretches where the lap's `off_track` channel is 1. Empty when not recorded. */
export function offTrackRuns(trace: LapTrace): DistanceRun[] {
  const flag = trace.channels.off_track;
  const dist = trace.channels.distance_m;
  if (!flag) return [];
  const runs: DistanceRun[] = [];
  let start: number | null = null;
  for (let i = 0; i < flag.length && i < dist.length; i++) {
    const on = (flag[i] ?? 0) >= 0.5;
    if (on && start === null) start = dist[i];
    if (!on && start !== null) {
      runs.push({ from: start, to: dist[i - 1] ?? start });
      start = null;
    }
  }
  if (start !== null) runs.push({ from: start, to: dist[Math.min(flag.length, dist.length) - 1] });
  return runs;
}
