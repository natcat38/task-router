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

/**
 * One before/after row of the replay diff. It is a container-query layout, not a
 * viewport one: in a narrow space (a phone, or the run page's side panel) Before
 * and After stack as two labelled lines, because four columns left each value
 * about 8 characters wide. Wide enough, it is the compact four-column row.
 * A changed row says so in text and with an arrow, never by colour alone.
 */
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
    <div className="@container">
      <div className="flex flex-col gap-0.5 font-mono text-[13px] @md:grid @md:grid-cols-[6rem_1fr_auto_1fr] @md:items-baseline @md:gap-2">
        <span className="text-fog">
          {label}
          {changed && (
            <span aria-hidden="true" className="@md:hidden">
              {" "}
              (changed)
            </span>
          )}
          <span className="sr-only">{changed ? " changed" : " unchanged"}</span>
        </span>
        <span className="flex gap-2 break-words">
          <span className="w-14 shrink-0 text-fog @md:hidden">Before</span>
          <span className="min-w-0 break-words text-signal">{before}</span>
        </span>
        <span aria-hidden="true" className="hidden text-fog @md:inline">
          {changed ? "→" : "="}
        </span>
        <span className="flex gap-2">
          <span className="w-14 shrink-0 text-fog @md:hidden">After</span>
          <span className={`min-w-0 break-words ${changed ? "text-tier-sonnet" : "text-signal"}`}>
            {changed && (
              <span aria-hidden="true" className="@md:hidden">
                →{" "}
              </span>
            )}
            {after}
          </span>
        </span>
      </div>
    </div>
  );
}

/** Both outputs in full, behind a disclosure, each in its own scrollable block. */
function FullOutput({ before, after }: { before: string | null; after: string | null }) {
  if (before === null && after === null) return null;
  return (
    <details className="group mt-1">
      <summary className="min-h-11 cursor-pointer py-2 font-mono text-[13px] text-signal underline decoration-line hover:decoration-signal md:min-h-0 md:py-1">
        Show full output
      </summary>
      <div className="mt-2 flex flex-col gap-3">
        {[
          { title: "Before (original run)", text: before },
          { title: "After (replay)", text: after },
        ].map(({ title, text }) => (
          <div key={title}>
            <h4 className="mb-1 text-xs text-fog">{title}</h4>
            <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words rounded bg-ink px-3 py-2 font-mono text-[13px] text-signal">
              {text ?? "-"}
            </pre>
          </div>
        ))}
      </div>
    </details>
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
            className="min-h-11 rounded border border-control-line bg-ink px-2 py-1.5 text-base text-signal md:min-h-0 md:text-sm"
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
          className="min-h-11 rounded border border-signal bg-signal px-4 py-1.5 text-sm font-medium text-ink transition-standard hover:bg-fog hover:border-fog disabled:cursor-not-allowed disabled:opacity-40 md:min-h-0"
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
          <FullOutput before={sourceRun.output_text} after={state.newRun?.output_text ?? null} />

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
