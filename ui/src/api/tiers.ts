import type { Tier } from "./types";

/**
 * The tier-color system -- the one signature element from
 * docs/Design_Direction.md. Every place that shows a tier (nav legend,
 * run rows, waterfall bars, replay diffs) reads from here, so the mapping
 * only ever lives in one place.
 */
export const TIER_ORDER: readonly Tier[] = ["local", "sonnet", "opus"];

export const TIER_COLOR: Record<Tier, string> = {
  local: "var(--tier-local)",
  sonnet: "var(--tier-sonnet)",
  opus: "var(--tier-opus)",
};

export const TIER_LABEL: Record<Tier, string> = {
  local: "local",
  sonnet: "sonnet",
  opus: "opus",
};

export function isTier(value: string | null | undefined): value is Tier {
  return value === "local" || value === "sonnet" || value === "opus";
}
