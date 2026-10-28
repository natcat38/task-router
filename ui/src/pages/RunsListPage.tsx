import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { describeApiError, getRuns } from "../api/client";
import type { Run, RunStatus, RunsListResponse } from "../api/types";
import { isTier, TIER_ORDER } from "../api/tiers";
import { StatusChip } from "../components/StatusChip";
import { RelativeTimestamp, Timestamp } from "../components/Timestamp";
import { requestSnippet } from "../lib/format";
import { useDocumentTitle } from "../lib/useDocumentTitle";
import { TierChip } from "../components/TierChip";
import { EmptyState, ErrorState, LoadingState } from "../components/StatusStates";

const PAGE_SIZE = 20;
const STATUS_OPTIONS: RunStatus[] = ["ok", "error"];
/** How long to wait after the last keystroke in "Use case" before filtering. */
const USE_CASE_DEBOUNCE_MS = 300;

function shortId(id: string): string {
  return id.length > 10 ? `${id.slice(0, 10)}…` : id;
}

/**
 * Runs list (Product_Scope §2 surface 1). Filters and the current page live
 * in the URL's query string -- not component state -- so a link to a
 * filtered/paginated view is shareable and the back button works, matching
 * how GET /runs itself is shaped around query params (Tech_Scope §4).
 */
export function RunsListPage() {
  useDocumentTitle("Runs");
  const [searchParams, setSearchParams] = useSearchParams();
  const page = Math.max(1, Number(searchParams.get("page") ?? "1") || 1);
  const tierParam = searchParams.get("tier") ?? "";
  const useCaseParam = searchParams.get("use_case") ?? "";
  const statusParam = searchParams.get("status") ?? "";
  const activeFilters = [tierParam, useCaseParam, statusParam].filter(Boolean).length;

  const [data, setData] = useState<RunsListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Under `sm` the three filters sit behind a "Filters (n)" button; from `sm` they are always shown.
  const [filtersOpen, setFiltersOpen] = useState(false);
  // What is typed in "Use case", kept apart from the URL so typing doesn't fire a request
  // and a history entry per keystroke.
  const [useCaseInput, setUseCaseInput] = useState(useCaseParam);

  // Only the newest request may update the page: a slow earlier response must not land
  // after a newer one and show results for the wrong filters.
  const latestRequest = useRef(0);

  const load = useCallback(() => {
    const requestId = ++latestRequest.current;
    const isLatest = () => requestId === latestRequest.current;
    setLoading(true);
    setError(null);
    getRuns({
      page,
      page_size: PAGE_SIZE,
      tier: isTier(tierParam) ? tierParam : undefined,
      use_case: useCaseParam || undefined,
      status: statusParam === "ok" || statusParam === "error" ? statusParam : undefined,
    })
      .then((res) => {
        if (isLatest()) setData(res);
      })
      .catch((err: unknown) => {
        if (isLatest()) setError(describeApiError(err));
      })
      .finally(() => {
        if (isLatest()) setLoading(false);
      });
  }, [page, tierParam, useCaseParam, statusParam]);

  useEffect(() => {
    load();
  }, [load]);

  function setFilter(key: "tier" | "use_case" | "status", value: string, replace = false) {
    const next = new URLSearchParams(searchParams);
    if (value) {
      next.set(key, value);
    } else {
      next.delete(key);
    }
    // Changing a filter invalidates the current page number.
    next.delete("page");
    setSearchParams(next, { replace });
  }

  // Back/forward or "Clear filters" changes the URL; mirror it into the text box.
  useEffect(() => {
    setUseCaseInput(useCaseParam);
  }, [useCaseParam]);

  // Apply the typed text 300 ms after the last keystroke. `replace` so a typed
  // word is one history entry at most, not one per letter.
  useEffect(() => {
    if (useCaseInput.trim() === useCaseParam) return;
    const timer = setTimeout(() => setFilter("use_case", useCaseInput.trim(), true), USE_CASE_DEBOUNCE_MS);
    return () => clearTimeout(timer);
    // setFilter closes over searchParams; re-running on every URL change would restart the timer.
  }, [useCaseInput]); // eslint-disable-line react-hooks/exhaustive-deps

  function goToPage(nextPage: number) {
    const next = new URLSearchParams(searchParams);
    next.set("page", String(nextPage));
    setSearchParams(next);
  }

  const runs = data?.data ?? [];
  const pagination = data?.pagination;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-[22px] font-semibold">Runs</h1>
        <button
          type="button"
          aria-expanded={filtersOpen}
          aria-controls="run-filters"
          onClick={() => setFiltersOpen((open) => !open)}
          className="min-h-11 rounded border border-line px-3 py-1.5 text-sm transition-standard hover:border-signal sm:hidden"
        >
          Filters{activeFilters > 0 ? ` (${activeFilters})` : ""}
        </button>
      </div>

      <form
        id="run-filters"
        aria-label="Filter runs"
        className={`${filtersOpen ? "flex" : "hidden"} flex-wrap items-end gap-3 sm:flex`}
        onSubmit={(event) => event.preventDefault()}
      >
        <label className="flex flex-col gap-1 text-xs text-fog">
          Tier
          <select
            value={tierParam}
            onChange={(event) => setFilter("tier", event.target.value)}
            className="rounded border border-line bg-panel px-2 py-1.5 text-sm text-signal"
          >
            <option value="">All</option>
            {TIER_ORDER.map((tier) => (
              <option key={tier} value={tier}>
                {tier}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1 text-xs text-fog">
          Use case
          <input
            type="text"
            value={useCaseInput}
            onChange={(event) => setUseCaseInput(event.target.value)}
            placeholder="any"
            className="rounded border border-line bg-panel px-2 py-1.5 text-sm text-signal placeholder:text-fog"
          />
        </label>

        <label className="flex flex-col gap-1 text-xs text-fog">
          Status
          <select
            value={statusParam}
            onChange={(event) => setFilter("status", event.target.value)}
            className="rounded border border-line bg-panel px-2 py-1.5 text-sm text-signal"
          >
            <option value="">All</option>
            {STATUS_OPTIONS.map((status) => (
              <option key={status} value={status}>
                {status}
              </option>
            ))}
          </select>
        </label>
      </form>

      {loading && <LoadingState message="Reading runs…" />}

      {!loading && error && <ErrorState message={error} onRetry={load} />}

      {!loading && !error && runs.length === 0 && activeFilters > 0 && (
        <EmptyState
          message="No runs match these filters."
          action={
            <button
              type="button"
              onClick={() => setSearchParams({})}
              className="rounded border border-line px-3 py-1.5 font-mono text-[13px] text-signal transition-standard hover:border-signal"
            >
              Clear filters
            </button>
          }
        />
      )}

      {!loading && !error && runs.length === 0 && activeFilters === 0 && (
        <EmptyState message="No runs yet. Send a request to POST /v1/completions and it'll show up here." />
      )}

      {!loading && !error && runs.length > 0 && (
        <>
          {/* Desktop / tablet: a real table, horizontal scroll only within its own container. */}
          <div className="hidden overflow-x-auto rounded border border-line sm:block">
            <table className="w-full min-w-[860px] text-left text-sm">
              <thead className="border-b border-line text-xs text-fog">
                <tr>
                  <th scope="col" className="w-2/5 px-3 py-2 font-normal">
                    Request
                  </th>
                  <th scope="col" className="px-3 py-2 font-normal">
                    Created
                  </th>
                  <th scope="col" className="px-3 py-2 font-normal">
                    Use case
                  </th>
                  <th scope="col" className="px-3 py-2 font-normal">
                    Tier
                  </th>
                  <th scope="col" className="px-3 py-2 font-normal">
                    Model
                  </th>
                  <th scope="col" className="px-3 py-2 font-normal">
                    Status
                  </th>
                  <th scope="col" className="px-3 py-2 font-normal">
                    Run
                  </th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <RunRow key={run.run_id} run={run} />
                ))}
              </tbody>
            </table>
          </div>

          {/* Below sm: stacked key/value cards instead of a horizontally-scrolled table. */}
          <ul className="flex flex-col gap-1.5 sm:hidden">
            {runs.map((run) => (
              <RunCard key={run.run_id} run={run} />
            ))}
          </ul>

          {pagination && (
            <nav
              aria-label="Runs pagination"
              className="flex items-center justify-between border-t border-line pt-3 font-mono text-[13px] text-fog"
            >
              <button
                type="button"
                onClick={() => goToPage(page - 1)}
                disabled={page <= 1}
                className="rounded border border-line px-3 py-1.5 transition-standard hover:border-signal disabled:cursor-not-allowed disabled:opacity-40"
              >
                Prev
              </button>
              <span>
                Page {pagination.page} of {Math.max(pagination.total_pages, 1)}
              </span>
              <button
                type="button"
                onClick={() => goToPage(page + 1)}
                disabled={page >= pagination.total_pages}
                className="rounded border border-line px-3 py-1.5 transition-standard hover:border-signal disabled:cursor-not-allowed disabled:opacity-40"
              >
                Next
              </button>
            </nav>
          )}
        </>
      )}
    </div>
  );
}

function EscalatedBadge() {
  return (
    <span className="rounded border border-line px-1.5 py-0.5 font-mono text-[11px] uppercase tracking-wide text-fog">
      escalated
    </span>
  );
}

function RunRow({ run }: { run: Run }) {
  const navigate = useNavigate();
  const href = `/runs/${encodeURIComponent(run.run_id)}`;
  return (
    // The whole row opens the run. The request link inside it is the keyboard and
    // screen-reader target; the click handler just widens the mouse target.
    <tr
      onClick={(event) => {
        if (!(event.target as HTMLElement).closest("a")) navigate(href);
      }}
      className="cursor-pointer border-b border-line transition-standard last:border-b-0 hover:bg-panel"
    >
      <td className="max-w-0 px-3 py-2">
        <Link
          to={href}
          title={run.input_text}
          className="block truncate text-signal underline decoration-line hover:decoration-signal"
        >
          {requestSnippet(run.input_text)}
        </Link>
      </td>
      <td className="whitespace-nowrap px-3 py-2 font-mono text-[13px] text-fog">
        <Timestamp iso={run.created_at} />
      </td>
      <td className="max-w-[12rem] truncate px-3 py-2" title={run.use_case ?? undefined}>
        {run.use_case ?? <span className="text-fog">-</span>}
      </td>
      <td className="px-3 py-2">
        <span className="inline-flex items-center gap-2">
          <TierChip tier={run.tier_chosen} />
          {run.escalated && <EscalatedBadge />}
        </span>
      </td>
      <td className="px-3 py-2 font-mono text-[13px]">{run.model_used}</td>
      <td className="px-3 py-2">
        <StatusChip status={run.status} />
      </td>
      <td className="px-3 py-2 font-mono text-[13px] text-fog" title={run.run_id}>
        {shortId(run.run_id)}
      </td>
    </tr>
  );
}

/** Phone row: two lines, and the whole row is the link. Line 1 is what was asked,
 * line 2 is how it went (tier, escalated, status, how long ago). */
function RunCard({ run }: { run: Run }) {
  return (
    <li>
      <Link
        to={`/runs/${encodeURIComponent(run.run_id)}`}
        title={run.input_text}
        className="flex min-h-14 flex-col justify-center gap-1 rounded border border-line bg-panel px-3 py-1.5 transition-standard hover:border-signal"
      >
        <span className="truncate text-signal">{requestSnippet(run.input_text)}</span>
        <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <TierChip tier={run.tier_chosen} />
          {run.escalated && <EscalatedBadge />}
          <StatusChip status={run.status} />
          <RelativeTimestamp iso={run.created_at} className="font-mono text-[13px] text-fog" />
        </span>
      </Link>
    </li>
  );
}
