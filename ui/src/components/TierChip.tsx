import type { Tier } from "../api/types";
import { TIER_COLOR, TIER_LABEL } from "../api/tiers";

interface TierChipProps {
  tier: Tier;
  /** Render just the dot, no label -- used in dense table cells. */
  dotOnly?: boolean;
}

/**
 * The tier chip: a filled dot in the tier's color plus its monospace label.
 * This is the signature element from Design_Direction.md, reused in the
 * nav legend, run-list rows, and (in later chunks) the waterfall and
 * replay diff.
 */
export function TierChip({ tier, dotOnly = false }: TierChipProps) {
  return (
    <span className="inline-flex items-center gap-1.5 font-mono text-[13px] text-signal">
      <span
        aria-hidden="true"
        className="inline-block h-2 w-2 shrink-0 rounded-full"
        style={{ backgroundColor: TIER_COLOR[tier] }}
      />
      {!dotOnly && <span>{TIER_LABEL[tier]}</span>}
      <span className="sr-only">{dotOnly ? `tier: ${TIER_LABEL[tier]}` : null}</span>
    </span>
  );
}
