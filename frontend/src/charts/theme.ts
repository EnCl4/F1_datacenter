import type uPlot from "uplot";

/** Canvas drawing cannot use `var(--x)`, so resolve the CSS variables to real colours. */
export interface ChartColors {
  fg: string;
  dim: string;
  line: string;
  panel: string;
  accent: string;
  /** Colour of the reference lap's series. */
  reference: string;
  green: string;
  amber: string;
  red: string;
}

export function chartColors(): ChartColors {
  const style = getComputedStyle(document.documentElement);
  const get = (name: string, fallback: string) => style.getPropertyValue(name).trim() || fallback;
  return {
    fg: get("--fg", "#e8e8ea"),
    dim: get("--dim", "#8b8d98"),
    line: get("--line", "#2a2d36"),
    panel: get("--panel", "#17181d"),
    accent: get("--accent", "#5b9dd9"),
    reference: get("--amber", "#e8b339"),
    green: get("--green", "#3ecf8e"),
    amber: get("--amber", "#e8b339"),
    red: get("--red", "#e5484d"),
  };
}

/** Tyre compound colour, from the same variables the lap table uses. */
export function compoundColor(name: string): string {
  const style = getComputedStyle(document.documentElement);
  const var_ =
    {
      soft: "--soft",
      medium: "--medium",
      hard: "--hard",
      intermediate: "--inter",
      wet: "--wet",
    }[name.toLowerCase()] ?? "--dim";
  return style.getPropertyValue(var_).trim() || "#8b8d98";
}

/** Axis styling shared by every chart so they read on the dark background. */
export function axisStyle(colors: ChartColors): Pick<
  uPlot.Axis,
  "stroke" | "grid" | "ticks" | "border"
> {
  return {
    stroke: colors.dim,
    grid: { stroke: colors.line, width: 1 },
    ticks: { stroke: colors.line, width: 1 },
    border: { stroke: colors.line, width: 1 },
  };
}

/** Fixed y-axis width so stacked charts keep their plot areas aligned. */
export const Y_AXIS_SIZE = 62;

/**
 * One colour per wheel, distinct on the dark background. Fronts are drawn solid and
 * rears dashed (see WHEEL_DASH) so the pairing never relies on colour alone.
 */
export function wheelColors(colors: ChartColors): Record<"fl" | "fr" | "rl" | "rr", string> {
  return { fl: colors.accent, fr: colors.amber, rl: colors.green, rr: "#b78cf2" };
}

export const WHEEL_DASH: Record<"fl" | "fr" | "rl" | "rr", number[] | undefined> = {
  fl: undefined,
  fr: undefined,
  rl: [6, 4],
  rr: [6, 4],
};
