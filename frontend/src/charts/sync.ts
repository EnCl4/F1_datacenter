import type uPlot from "uplot";

/**
 * Every chart on the compare page shares this key: uPlot then mirrors the cursor
 * position between them (FR-011), and the hooks below mirror the x zoom (FR-012).
 */
/** Options the wrapper completes with width/height. */
export type ChartOptions = Omit<uPlot.Options, "width" | "height">;

export const SYNC_KEY = "f1dc-trace";

// Live charts per sync key. Charts register once constructed and leave on destroy.
const registry = new Map<string, Set<uPlot>>();

// True while we are pushing a scale to the other charts. Each setScale() we issue
// fires the `setScale` hook on the receiving chart, which would push it straight
// back and recurse forever; this flag makes those echoes no-ops.
let propagating = false;

type HookList<K extends keyof uPlot.Hooks.Defs> = NonNullable<uPlot.Hooks.Arrays[K]>;

function appendHook<K extends keyof uPlot.Hooks.Defs>(
  hooks: uPlot.Hooks.Arrays,
  name: K,
  fn: uPlot.Hooks.Defs[K],
): void {
  const list = (hooks[name] ?? []) as HookList<K>;
  (hooks as Record<string, unknown>)[name] = [...list, fn];
}

/**
 * Returns a copy of `opts` with cursor sync and zoom sync wired in.
 *
 * Zoom works by listening to `setScale` for the "x" scale (fired both by drag-select
 * and by double-click-to-reset) and copying the new range to every other chart.
 */
export function withSync(opts: ChartOptions, key: string = SYNC_KEY): ChartOptions {
  const hooks: uPlot.Hooks.Arrays = { ...(opts.hooks ?? {}) };

  // Register only once fully constructed: during construction the scale is still
  // being initialised and must not drag other charts' zoom along with it.
  appendHook(hooks, "ready", (u) => {
    let set = registry.get(key);
    if (!set) registry.set(key, (set = new Set()));
    set.add(u);
  });

  appendHook(hooks, "setScale", (u, scaleKey) => {
    if (scaleKey !== "x" || propagating) return;
    const { min, max } = u.scales.x;
    if (min == null || max == null) return;
    propagating = true;
    try {
      for (const other of registry.get(key) ?? []) {
        if (other === u) continue;
        const s = other.scales.x;
        if (s.min !== min || s.max !== max) other.setScale("x", { min, max });
      }
    } finally {
      propagating = false;
    }
  });

  appendHook(hooks, "destroy", (u) => {
    registry.get(key)?.delete(u);
  });

  return {
    ...opts,
    hooks,
    cursor: {
      ...(opts.cursor ?? {}),
      // setSeries off: highlighting one series everywhere would just be noise.
      sync: { key, setSeries: false },
      drag: { x: true, y: false, setScale: true },
    },
    scales: { ...(opts.scales ?? {}), x: { time: false, ...(opts.scales?.x ?? {}) } },
  };
}

/**
 * `setCursor` hook that reports the distance (metres) under the pointer, or null
 * when the pointer leaves. Attach to a single chart: cursors are synced, so one
 * chart sees every movement.
 */
export function cursorDistanceHook(
  report: (distance: number | null) => void,
): (u: uPlot) => void {
  let last: number | null | undefined;
  return (u) => {
    const { left, idx } = u.cursor;
    const next =
      left != null && left >= 0 && idx != null ? (u.data[0][idx] ?? null) : null;
    if (next !== last) {
      last = next;
      report(next);
    }
  };
}

/** Draws vertical dashed lines at the given x values (sector boundaries, FR-013). */
export function sectorLinesHook(
  distances: number[],
  color: string,
): (u: uPlot) => void {
  return (u) => {
    const { ctx, bbox } = u;
    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = Math.max(1, devicePixelRatio);
    ctx.setLineDash([5 * devicePixelRatio, 4 * devicePixelRatio]);
    for (const d of distances) {
      const x = Math.round(u.valToPos(d, "x", true));
      if (x < bbox.left || x > bbox.left + bbox.width) continue;
      ctx.beginPath();
      ctx.moveTo(x, bbox.top);
      ctx.lineTo(x, bbox.top + bbox.height);
      ctx.stroke();
    }
    ctx.restore();
  };
}
