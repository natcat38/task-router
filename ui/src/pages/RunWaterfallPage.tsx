import { Fragment, useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { ApiError, describeApiError, getRunSpans } from "../api/client";
import type { Run, RunSpansResponse, Span, Tier } from "../api/types";
import { TIER_COLOR, TIER_LABEL } from "../api/tiers";
import { TierChip } from "../components/TierChip";
import { ReplayPanel } from "../components/ReplayPanel";
import { EmptyState, ErrorState, LoadingState } from "../components/StatusStates";

/** A span plus its nesting depth, in the preorder the waterfall renders it. */
interface SpanNode {
  span: Span;
  depth: number;
}

/**
 * Turns the flat `spans` array into a depth-annotated, parent-first render
 * order. Siblings are ordered by `start_ns` so the waterfall reads
 * top-to-bottom in the same order the trace actually happened. A span whose
 * `parent_span_id` doesn't match any span in this response (root spans have
 * `parent_span_id: null`, but a truncated export could also orphan a span)
 * is treated as a root rather than dropped, so the trace never silently
 * loses rows. A `visited` guard stops a malformed parent cycle from looping
 * forever.
 */
function flattenSpans(spans: Span[]): SpanNode[] {
  const byParent = new Map<string | null, Span[]>();
  for (const span of spans) {
    const list = byParent.get(span.parent_span_id) ?? [];
    list.push(span);
    byParent.set(span.parent_span_id, list);
  }
  for (const list of byParent.values()) {
    list.sort((a, b) => a.start_ns - b.start_ns);
  }

  const knownIds = new Set(spans.map((s) => s.span_id));
  const roots = spans.filter(
    (s) => s.parent_span_id === null || !knownIds.has(s.parent_span_id),
  );
  roots.sort((a, b) => a.start_ns - b.start_ns);

  const result: SpanNode[] = [];
  const visited = new Set<string>();

  function visit(span: Span, depth: number) {
    if (visited.has(span.span_id)) return;
    visited.add(span.span_id);
    result.push({ span, depth });
    const children = byParent.get(span.span_id) ?? [];
    for (const child of children) visit(child, depth + 1);
  }

  for (const root of roots) visit(root, 0);
  return result;
}

function durationMs(span: Span): number {
  return (span.end_ns - span.start_ns) / 1_000_000;
}

/** Span names follow Tech_Scope §3: `chat <model>` for an answering call.
 * The model id tells us which tier answered -- `sonnet`/`opus` are the
 * cloud-tier model ids in registry.yaml, anything else (e.g. `qwen3:1.7b`)
 * is the local tier. Non-chat spans (classify/select_tier/judge/escalate)
 * aren't tier-specific, so they get no tier color. */
function inferSpanTier(spanName: string): Tier | null {
  const match = /^chat (.+)$/.exec(spanName);
  if (!match) return null;
  const model = match[1];
  if (model === "sonnet") return "sonnet";
  if (model === "opus") return "opus";
  return "local";
}

function shortId(id: string): string {
  return id.length > 10 ? `${id.slice(0, 10)}…` : id;
}

function EscalatedBadge() {
  return (
    <span className="rounded border border-line px-1.5 py-0.5 font-mono text-[11px] uppercase tracking-wide text-fog">
      escalated
    </span>
  );
}

function ForcedTierBadge({ tier }: { tier: Tier }) {
  return (
    <span className="rounded border border-line px-1.5 py-0.5 font-mono text-[11px] text-fog">
      replay, forced {TIER_LABEL[tier]}
    </span>
  );
}

function RunHeader({ run }: { run: Run }) {
  return (
    <div className="flex flex-col gap-3 rounded border border-line bg-panel px-5 py-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="break-all font-mono text-[18px] font-semibold text-signal sm:text-[22px]">
          Run {run.run_id}
        </h1>
        <span className="font-mono text-[13px] text-fog">{run.status}</span>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <TierChip tier={run.tier_chosen} />
        <span className="font-mono text-[13px] text-fog">{run.model_used}</span>
        {run.escalated && <EscalatedBadge />}
        {run.forced_tier && <ForcedTierBadge tier={run.forced_tier} />}
      </div>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-fog sm:grid-cols-4">
        <dt>Use case</dt>
        <dd className="text-signal">{run.use_case ?? "-"}</dd>
        <dt>Judge score</dt>
        <dd className="text-signal">
          {run.judge_score === null ? "not judged" : `${run.judge_score} (${run.judge_label ?? "-"})`}
        </dd>
        <dt>Duration</dt>
        <dd className="text-signal">
          {run.total_duration_ms === null ? "-" : `${run.total_duration_ms}ms`}
        </dd>
        <dt>Created</dt>
        <dd className="text-signal">{run.created_at}</dd>
      </dl>
    </div>
  );
}

function TimeAxis({ totalRangeMs }: { totalRangeMs: number }) {
  const ticks = [0, 0.25, 0.5, 0.75, 1];
  return (
    <div
      aria-hidden="true"
      className="relative ml-28 h-5 border-b border-line sm:ml-48"
    >
      {ticks.map((t) => (
        <span
          key={t}
          className="absolute top-0 -translate-x-1/2 font-mono text-[11px] text-fog"
          style={{ left: `${t * 100}%` }}
        >
          {(t * totalRangeMs).toFixed(0)}ms
        </span>
      ))}
    </div>
  );
}

function SpanRow({
  node,
  minStart,
  totalRange,
  isSelected,
  onSelect,
}: {
  node: SpanNode;
  minStart: number;
  totalRange: number;
  isSelected: boolean;
  onSelect: (span: Span) => void;
}) {
  const { span, depth } = node;
  const tier = inferSpanTier(span.name);
  const leftPct = ((span.start_ns - minStart) / totalRange) * 100;
  const widthPct = Math.max(((span.end_ns - span.start_ns) / totalRange) * 100, 0.5);

  return (
    <button
      type="button"
      onClick={() => onSelect(span)}
      aria-expanded={isSelected}
      className={`flex w-full items-center gap-2 rounded px-1 py-1 text-left transition-standard hover:bg-ink ${
        isSelected ? "bg-ink" : ""
      }`}
    >
      <span
        className="w-28 shrink-0 truncate font-mono text-[13px] text-signal sm:w-48"
        style={{ paddingLeft: `${depth * 12}px` }}
        title={span.name}
      >
        {span.name}
      </span>
      <span className="relative h-4 flex-1 rounded-sm bg-ink">
        <span
          className="absolute top-0 h-full rounded-sm motion-safe:transition-standard"
          style={{
            left: `${leftPct}%`,
            width: `${widthPct}%`,
            backgroundColor: tier ? TIER_COLOR[tier] : "var(--line)",
          }}
        />
      </span>
      <span className="w-16 shrink-0 text-right font-mono text-[13px] text-fog">
        {durationMs(span).toFixed(1)}ms
      </span>
    </button>
  );
}

function AttributeDrawer({ span, onClose }: { span: Span; onClose: () => void }) {
  const entries = Object.entries(span.attributes ?? {});
  const genAiEntries = entries.filter(([key]) => key.startsWith("gen_ai."));
  const otherEntries = entries.filter(([key]) => !key.startsWith("gen_ai."));

  return (
    <section
      aria-label={`Attributes for ${span.name}`}
      className="rounded border border-line bg-panel px-5 py-4"
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="break-all font-mono text-[13px] font-semibold text-signal">{span.name}</h2>
        <button
          type="button"
          onClick={onClose}
          className="shrink-0 rounded border border-line px-2 py-1 font-mono text-[11px] transition-standard hover:border-signal"
        >
          Close
        </button>
      </div>

      {genAiEntries.length > 0 && (
        <div className="mb-3">
          <h3 className="mb-1 text-xs text-fog">gen_ai attributes</h3>
          <dl className="grid grid-cols-[minmax(0,auto)_1fr] gap-x-3 gap-y-1 font-mono text-[13px]">
            {genAiEntries.map(([key, value]) => (
              <Fragment key={key}>
                <dt className="break-all text-fog">{key}</dt>
                <dd className="break-all text-signal">{JSON.stringify(value)}</dd>
              </Fragment>
            ))}
          </dl>
        </div>
      )}

      {otherEntries.length === 0 && genAiEntries.length === 0 ? (
        <p className="text-fog">No attributes recorded for this span.</p>
      ) : (
        <div>
          <h3 className="mb-1 text-xs text-fog">Raw attributes</h3>
          <pre className="overflow-x-auto rounded bg-ink px-3 py-2 font-mono text-[12px] text-fog">
            {JSON.stringify(span.attributes, null, 2)}
          </pre>
        </div>
      )}
    </section>
  );
}

/**
 * Span waterfall for one run (Product_Scope §2 surface 2): the run header,
 * a replay-and-diff panel, and the span waterfall itself, driven by
 * GET /runs/{id}/spans (Tech_Scope §4).
 */
export function RunWaterfallPage() {
  const { runId } = useParams<{ runId: string }>();

  const [data, setData] = useState<RunSpansResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [selectedSpan, setSelectedSpan] = useState<Span | null>(null);

  const load = useCallback(() => {
    if (!runId) return;
    setLoading(true);
    setError(null);
    setNotFound(false);
    setSelectedSpan(null);
    getRunSpans(runId)
      .then(setData)
      .catch((err: unknown) => {
        if (err instanceof ApiError && err.status === 404) {
          setNotFound(true);
        } else {
          setError(describeApiError(err));
        }
      })
      .finally(() => setLoading(false));
  }, [runId]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return <LoadingState message="Reading trace…" />;
  }

  if (notFound) {
    return <EmptyState message="No run with this ID. It may have aged out or the ID is wrong." />;
  }

  if (error || !data) {
    return <ErrorState message={error ?? "Something went wrong."} onRetry={load} />;
  }

  const { run, spans } = data;
  const nodes = flattenSpans(spans);
  const minStart = spans.length > 0 ? Math.min(...spans.map((s) => s.start_ns)) : 0;
  const maxEnd = spans.length > 0 ? Math.max(...spans.map((s) => s.end_ns)) : 0;
  const totalRange = Math.max(maxEnd - minStart, 1);
  const totalRangeMs = totalRange / 1_000_000;

  return (
    <div className="flex flex-col gap-6">
      <RunHeader run={run} />

      <ReplayPanel sourceRunId={run.run_id} sourceRun={run} />

      <section aria-label="Span waterfall" className="rounded border border-line bg-panel px-5 py-4">
        <h2 className="mb-3 text-base font-semibold text-signal">Waterfall</h2>

        {spans.length === 0 ? (
          <EmptyState message="This run has no recorded spans." />
        ) : (
          <>
            <TimeAxis totalRangeMs={totalRangeMs} />
            <div role="list" aria-label="Spans" className="mt-2 flex flex-col gap-0.5">
              {nodes.map((node) => (
                <div role="listitem" key={node.span.span_id}>
                  <SpanRow
                    node={node}
                    minStart={minStart}
                    totalRange={totalRange}
                    isSelected={selectedSpan?.span_id === node.span.span_id}
                    onSelect={setSelectedSpan}
                  />
                </div>
              ))}
            </div>
          </>
        )}
      </section>

      {selectedSpan && (
        <AttributeDrawer span={selectedSpan} onClose={() => setSelectedSpan(null)} />
      )}
    </div>
  );
}

export { shortId };
