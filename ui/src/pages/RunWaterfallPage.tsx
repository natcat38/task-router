import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import type { Ref } from "react";
import { useParams } from "react-router-dom";
import { ApiError, describeApiError, getRunSpans } from "../api/client";
import type { Run, RunSpansResponse, Span, Tier } from "../api/types";
import { TIER_COLOR, TIER_LABEL } from "../api/tiers";
import { TierChip } from "../components/TierChip";
import { ReplayPanel } from "../components/ReplayPanel";
import { RequestResponse, RunInspector, inspectorPanelId } from "../components/RunInspector";
import type { InspectorTab } from "../components/RunInspector";
import { StatusChip } from "../components/StatusChip";
import { Timestamp } from "../components/Timestamp";
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
        <StatusChip status={run.status} />
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
        <dd className="text-signal">
          <Timestamp iso={run.created_at} />
        </dd>
      </dl>
    </div>
  );
}

/**
 * The waterfall's three columns, shared by the axis and every row so the axis
 * can never drift from the bars again (it used to run 76 px wider than them):
 * a name column, the flexible bar track, and a duration column. The widths
 * and the row's `gap-2 px-1` live here, once.
 */
const ROW_LAYOUT = "flex w-full items-center gap-2 px-1";
const NAME_COL = "w-28 shrink-0 sm:w-40 2xl:w-48";
const DURATION_COL = "w-16 shrink-0";

/** Under `sm` the bar track is only about 120 px wide, so the axis keeps just
 * the start and end labels (and only the end label on the narrowest phones)
 * instead of printing five labels on top of each other. */
function TimeAxis({ totalRangeMs }: { totalRangeMs: number }) {
  const ticks = [0, 0.25, 0.5, 0.75, 1];
  return (
    <div aria-hidden="true" data-testid="time-axis" className={ROW_LAYOUT}>
      <span className={NAME_COL} />
      <div className="relative h-5 flex-1 border-b border-line">
        {ticks.map((t) => (
          <span
            key={t}
            className={`absolute top-0 font-mono text-[11px] text-fog ${
              t === 0
                ? "max-[339px]:hidden"
                : t === 1
                  ? "-translate-x-full"
                  : "hidden -translate-x-1/2 sm:block"
            }`}
            style={{ left: `${t * 100}%` }}
          >
            {(t * totalRangeMs).toFixed(0)}ms
          </span>
        ))}
      </div>
      <span className={DURATION_COL} />
    </div>
  );
}

function SpanRow({
  node,
  totalRange,
  minStart,
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
  const widthPct = Math.min(
    Math.max(((span.end_ns - span.start_ns) / totalRange) * 100, 0.5),
    100,
  );
  // Keep the minimum-width sliver inside the track instead of hanging past the end.
  const leftPct = Math.min(((span.start_ns - minStart) / totalRange) * 100, 100 - widthPct);

  return (
    <button
      type="button"
      data-span-id={span.span_id}
      onClick={() => onSelect(span)}
      aria-expanded={isSelected}
      aria-controls={inspectorPanelId("span")}
      className={`${ROW_LAYOUT} rounded py-1 text-left transition-standard hover:bg-ink ${
        isSelected ? "bg-ink" : ""
      }`}
    >
      <span
        className={`${NAME_COL} truncate font-mono text-[13px] text-signal`}
        style={{ paddingLeft: `${depth * 12}px` }}
        title={span.name}
      >
        {span.name}
      </span>
      <span data-testid="span-track" className="relative h-4 flex-1 rounded-sm bg-ink">
        <span
          data-testid="span-bar"
          className="absolute top-0 h-full rounded-sm motion-safe:transition-standard"
          style={{
            left: `${leftPct}%`,
            width: `${widthPct}%`,
            backgroundColor: tier ? TIER_COLOR[tier] : "var(--line)",
          }}
        />
      </span>
      <span className={`${DURATION_COL} text-right font-mono text-[13px] text-fog`}>
        {durationMs(span).toFixed(1)}ms
      </span>
    </button>
  );
}

function AttributeDrawer({
  span,
  onClose,
  headingRef,
}: {
  span: Span;
  onClose: () => void;
  headingRef: Ref<HTMLHeadingElement>;
}) {
  const entries = Object.entries(span.attributes ?? {});
  const genAiEntries = entries.filter(([key]) => key.startsWith("gen_ai."));
  const otherEntries = entries.filter(([key]) => !key.startsWith("gen_ai."));

  return (
    <section aria-label={`Attributes for ${span.name}`}>
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2
          ref={headingRef}
          tabIndex={-1}
          className="break-all font-mono text-[13px] font-semibold text-signal"
        >
          {span.name}
        </h2>
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
 * Span waterfall for one run (Product_Scope §2 surface 2): the run header, the
 * span waterfall, and an inspector panel (span details, request/response,
 * replay-and-diff) beside it from `lg` and below it on a phone, driven by
 * GET /runs/{id}/spans (Tech_Scope §4).
 */
export function RunWaterfallPage() {
  const { runId } = useParams<{ runId: string }>();

  const [data, setData] = useState<RunSpansResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [selectedSpan, setSelectedSpan] = useState<Span | null>(null);
  const [activeTab, setActiveTab] = useState<InspectorTab>("replay");
  const inspectorRef = useRef<HTMLElement>(null);
  const spanHeadingRef = useRef<HTMLHeadingElement>(null);

  // Picking a span opens its details in the inspector. When the inspector sits
  // below the waterfall (under `xl`) it may be off screen, so scroll it into
  // view and move focus to its heading. Beside the waterfall it is already
  // visible, so focus stays on the row and arrow/tab navigation keeps its place.
  const selectedSpanId = selectedSpan?.span_id;
  useEffect(() => {
    if (!selectedSpanId) return;
    const stacked = !window.matchMedia?.("(min-width: 1280px)").matches;
    inspectorRef.current?.scrollIntoView?.({ block: "nearest" });
    if (stacked) spanHeadingRef.current?.focus({ preventScroll: true });
  }, [selectedSpanId]);

  // Escape closes the span details and hands focus back to the row.
  useEffect(() => {
    if (!selectedSpanId) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape" || event.defaultPrevented) return;
      const target = event.target;
      if (target instanceof HTMLElement && target.matches("select, input, textarea")) return;
      setSelectedSpan(null);
      document
        .querySelector<HTMLElement>(`[data-span-id="${CSS.escape(selectedSpanId as string)}"]`)
        ?.focus();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [selectedSpanId]);

  function selectSpan(span: Span) {
    setSelectedSpan(span);
    setActiveTab("span");
  }

  function closeSpan() {
    const id = selectedSpan?.span_id;
    setSelectedSpan(null);
    if (id) {
      document.querySelector<HTMLElement>(`[data-span-id="${CSS.escape(id)}"]`)?.focus();
    }
  }

  const load = useCallback(() => {
    if (!runId) return;
    setLoading(true);
    setError(null);
    setNotFound(false);
    setSelectedSpan(null);
    setActiveTab("replay");
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

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_24rem] xl:items-start">
        <section aria-label="Span waterfall" className="min-w-0 rounded border border-line bg-panel px-5 py-4">
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
                      onSelect={selectSpan}
                    />
                  </div>
                ))}
              </div>
            </>
          )}
        </section>

        <RunInspector
          active={activeTab}
          onChange={setActiveTab}
          panelRef={inspectorRef}
          span={
            selectedSpan ? (
              <AttributeDrawer span={selectedSpan} onClose={closeSpan} headingRef={spanHeadingRef} />
            ) : (
              <>
                <h2 className="mb-1 text-base font-semibold text-signal">Span details</h2>
                <p className="text-fog">Select a span in the waterfall to see its attributes.</p>
              </>
            )
          }
          request={<RequestResponse run={run} />}
          replay={<ReplayPanel sourceRunId={run.run_id} sourceRun={run} embedded />}
        />
      </div>
    </div>
  );
}

export { shortId };
