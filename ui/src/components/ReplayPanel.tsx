import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { describeApiError, getRunSpans, postReplay } from "../api/client";
import type { DiffSummary, Run, Tier } from "../api/types";
import { TIER_LABEL, TIER_ORDER } from "../api/tiers";

function shortId(id: string): string {
  return id.length > 10 ? `${id.slice(0, 10)}…` : id;
}

function truncate(text: string | null, max = 80): string {
  if (text === null) return "-";
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

type ReplayState =
  | { status: "idle" }
  | { status: "loading"; tier: Tier }
  | { status: "success"; diff: DiffSummary; newRunId: string; newRun: Run | null }
  | { status: "error"; message: string };

function DiffField({
  label,
  before,
  after,
  changed,
}: {
  label: string;
  before: string;
  after: string;
  changed: boolean;
}) {
  return (
    <div className="grid grid-cols-[6rem_1fr_auto_1fr] items-baseline gap-2 font-mono text-[13px]">
      <span className="text-fog">{label}</span>
      <span className="break-all text-signal">{before}</span>
      <span aria-hidden="true" className="text-fog">
        →
      </span>
      <span className={`break-all ${changed ? "text-tier-sonnet" : "text-signal"}`}>{after}</span>
    </div>
  );
}

/**
 * Replay-and-diff panel (Product_Scope §2 surface 3, Tech_Scope §4
 * POST /replay). Lives on the run-detail waterfall page with `sourceRunId`
 * fixed to the run being viewed; the standalone `/runs/:runId/replay` route
 * reuses it the same way.
 *
 * Per ADR 0002, replay is non-deterministic and re-runs the whole pipeline
 * with the tier forced -- it is never presented as a correction of the
 * original run, only as a new, separate run to compare against it.
 */
export function ReplayPanel({
  sourceRunId,
  sourceRun,
  embedded = false,
}: {
  sourceRunId: string;
  sourceRun: Run;
  /** Inside the run inspector, which already is the card: drop this one's own border and padding. */
  embedded?: boolean;
}) {
  const [tier, setTier] = useState<Tier>("sonnet");
  const [state, setState] = useState<ReplayState>({ status: "idle" });
  const resultHeadingRef = useRef<HTMLHeadingElement>(null);

  // A finished replay can land below the fold (always on a phone): bring it
  // into view and move focus to it so keyboard and screen-reader users land on it.
  useEffect(() => {
    if (state.status !== "success") return;
    const heading = resultHeadingRef.current;
    if (!heading) return;
    heading.scrollIntoView?.({ block: "nearest" });
    heading.focus({ preventScroll: true });
  }, [state.status]);

  function runReplay() {
    setState({ status: "loading", tier });
    postReplay({ source_run_id: sourceRunId, forced_tier: tier })
      .then(async (res) => {
        let newRun: Run | null = null;
        try {
          const spansRes = await getRunSpans(res.new_run_id);
          newRun = spansRes.run;
        } catch {
          // The diff summary and the link to the new run still work even if
          // this follow-up fetch fails -- don't fail the whole replay over it.
          newRun = null;
        }
        setState({ status: "success", diff: res.diff_summary, newRunId: res.new_run_id, newRun });
      })
      .catch((err: unknown) => setState({ status: "error", message: describeApiError(err) }));
  }

  const isLoading = state.status === "loading";

  return (
    <section
      aria-label="Replay with a forced tier"
      className={embedded ? "" : "rounded border border-line bg-panel px-5 py-4"}
    >
      <h2 className="mb-1 text-base font-semibold text-signal">Replay with a forced tier</h2>
      <p className="mb-3 text-fog">Pick a past run and a tier to force, then compare.</p>

      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-xs text-fog">
          Forced tier
          <select
            value={tier}
            onChange={(event) => setTier(event.target.value as Tier)}
            disabled={isLoading}
            className="rounded border border-line bg-ink px-2 py-1.5 text-sm text-signal"
          >
            {TIER_ORDER.map((t) => (
              <option key={t} value={t}>
                {TIER_LABEL[t]}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={runReplay}
          disabled={isLoading}
          className="rounded border border-line px-3 py-1.5 text-sm transition-standard hover:border-signal disabled:cursor-not-allowed disabled:opacity-40"
        >
          Replay
        </button>
      </div>

      {state.status === "loading" && (
        <p role="status" className="mt-3 flex items-center gap-2 text-fog">
          <span
            aria-hidden="true"
            className="h-3 w-3 shrink-0 animate-pulse rounded-full bg-fog motion-reduce:animate-none"
          />
          Replaying against {TIER_LABEL[state.tier]}…
        </p>
      )}

      {state.status === "error" && (
        <p role="alert" className="mt-3 text-tier-opus">
          Replay failed: {state.message}
        </p>
      )}

      {state.status === "success" && (
        <div className="mt-4 flex flex-col gap-2 border-t border-line pt-4">
          <h3
            ref={resultHeadingRef}
            tabIndex={-1}
            className="text-sm font-semibold text-signal"
          >
            Replay result
          </h3>
          <DiffField
            label="Tier"
            before={sourceRun.tier_chosen}
            after={state.newRun?.tier_chosen ?? "see new run"}
            changed={state.diff.tier_changed}
          />
          <DiffField
            label="Model"
            before={sourceRun.model_used}
            after={state.newRun?.model_used ?? "see new run"}
            changed={state.diff.model_changed}
          />
          <DiffField
            label="Judge score"
            before={sourceRun.judge_score === null ? "not judged" : String(sourceRun.judge_score)}
            after={
              state.newRun?.judge_score == null
                ? "not judged"
                : String(state.newRun.judge_score)
            }
            changed={state.diff.judge_score_delta !== null && state.diff.judge_score_delta !== 0}
          />
          <DiffField
            label="Output"
            before={truncate(sourceRun.output_text)}
            after={truncate(state.newRun?.output_text ?? null)}
            changed={state.diff.output_changed}
          />

          <p className="mt-2 max-w-prose text-xs text-fog">
            This replay re-ran the whole router pipeline with the tier forced and produced a new,
            separate run -- model output isn't reproducible run to run, so this does not correct
            or overwrite the original (ADR 0002). Compare the two; don't treat the new run as
            authoritative.
          </p>

          <Link
            to={`/runs/${encodeURIComponent(state.newRunId)}`}
            className="mt-1 font-mono text-[13px] text-signal underline decoration-line hover:decoration-signal"
          >
            View new run {shortId(state.newRunId)}
          </Link>
        </div>
      )}
    </section>
  );
}
