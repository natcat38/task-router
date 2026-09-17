import { useCallback, useEffect, useState } from "react";
import { describeApiError, getStats } from "../api/client";
import type { StatsResponse } from "../api/types";
import { TIER_COLOR, TIER_ORDER } from "../api/tiers";
import { TierChip } from "../components/TierChip";
import { EmptyState, ErrorState, LoadingState } from "../components/StatusStates";

function formatPct(value: number): string {
  return `${value.toFixed(1)}%`;
}

function StatTile({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="rounded border border-line bg-panel px-4 py-4">
      <div className="text-xs text-fog">{label}</div>
      <div className="mt-1 font-mono text-[22px] font-semibold text-signal">{value}</div>
      <p className="mt-1 text-xs text-fog">{hint}</p>
    </div>
  );
}

/**
 * Savings / honesty stats (Product_Scope §2 surface 4, §4 honesty labels).
 * The two saved-percentage figures are shown side by side, never one alone
 * -- Tech_Scope §4/§6 is explicit that hiding the judge-inclusive figure
 * overstates the local tier's saving.
 */
export function StatsPage() {
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    getStats()
      .then(setStats)
      .catch((err: unknown) => setError(describeApiError(err)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return <LoadingState message="Adding it up…" />;
  }

  if (error) {
    return <ErrorState message={error} onRetry={load} />;
  }

  if (!stats || stats.n_requests === 0) {
    return <EmptyState message="No completed runs yet — stats need at least one." />;
  }

  const maxTierCount = Math.max(...TIER_ORDER.map((tier) => stats.by_tier[tier] ?? 0), 1);

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[22px] font-semibold">Stats</h1>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatTile label="Requests" value={String(stats.n_requests)} hint="Total logged runs." />
        <StatTile
          label="Saved, excluding judge cost"
          value={formatPct(stats.saved_pct_excl_judge)}
          hint="Local tier's saving vs. always using the top tier -- judge calls not counted."
        />
        <StatTile
          label="Saved, including judge cost"
          value={formatPct(stats.saved_pct_incl_judge)}
          hint="Same comparison, with the judge call's own cost counted against the saving."
        />
      </div>

      <p className="max-w-prose text-fog">
        Savings at API list prices — no money changed hands. Both figures are computed
        from registry prices against measured token counts, not billed spend.
      </p>

      <section className="rounded border border-line bg-panel px-5 py-4" aria-label="Requests by tier">
        <h2 className="mb-3 text-base font-semibold text-signal">By tier</h2>
        <div className="flex flex-col gap-2">
          {TIER_ORDER.map((tier) => {
            const count = stats.by_tier[tier] ?? 0;
            const share = stats.n_requests > 0 ? (count / stats.n_requests) * 100 : 0;
            const barWidth = count > 0 ? Math.max((count / maxTierCount) * 100, 2) : 0;
            return (
              <div key={tier} className="flex items-center gap-3">
                <div className="w-20 shrink-0">
                  <TierChip tier={tier} />
                </div>
                <div className="h-3 flex-1 overflow-hidden rounded-full bg-ink">
                  <div
                    className="h-full rounded-full motion-safe:transition-standard"
                    style={{ width: `${barWidth}%`, backgroundColor: TIER_COLOR[tier] }}
                  />
                </div>
                <span className="w-28 shrink-0 text-right font-mono text-[13px] text-fog">
                  {count} ({share.toFixed(0)}%)
                </span>
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}
