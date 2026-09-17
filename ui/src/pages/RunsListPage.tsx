import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { describeApiError, getRuns } from "../api/client";
import type { Run, RunStatus, RunsListResponse } from "../api/types";
import { isTier, TIER_ORDER } from "../api/tiers";
import { TierChip } from "../components/TierChip";
import { EmptyState, ErrorState, LoadingState } from "../components/StatusStates";

const PAGE_SIZE = 20;
const STATUS_OPTIONS: RunStatus[] = ["ok", "error"];

function shortId(id: string): string {
  return id.length > 10 ? `${id.slice(0, 10)}…` : id;
}

function formatTimestamp(iso: string): string {
  const parsed = new Date(iso);
  return Number.isNaN(parsed.getTime()) ? iso : parsed.toLocaleString();
}

/**
 * Runs list (Product_Scope §2 surface 1). Filters and the current page live
 * in the URL's query string -- not component state -- so a link to a
 * filtered/paginated view is shareable and the back button works, matching
 * how GET /runs itself is shaped around query params (Tech_Scope §4).
 */
export function RunsListPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const page = Math.max(1, Number(searchParams.get("page") ?? "1") || 1);
  const tierParam = searchParams.get("tier") ?? "";
  const useCaseParam = searchParams.get("use_case") ?? "";
  const statusParam = searchParams.get("status") ?? "";

  const [data, setData] = useState<RunsListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    getRuns({
      page,
      page_size: PAGE_SIZE,
      tier: isTier(tierParam) ? tierParam : undefined,
      use_case: useCaseParam || undefined,
      status: statusParam === "ok" || statusParam === "error" ? statusParam : undefined,
    })
      .then(setData)
      .catch((err: unknown) => setError(describeApiError(err)))
      .finally(() => setLoading(false));
  }, [page, tierParam, useCaseParam, statusParam]);

  useEffect(() => {
    load();
  }, [load]);

  function setFilter(key: "tier" | "use_case" | "status", value: string) {
    const next = new URLSearchParams(searchParams);
    if (value) {
      next.set(key, value);
    } else {
      next.delete(key);
    }
    // Changing a filter invalidates the current page number.
    next.delete("page");
    setSearchParams(next);
  }

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
      </div>

      <form
        aria-label="Filter runs"
        className="flex flex-wrap items-end gap-3"
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
            value={useCaseParam}
            onChange={(event) => setFilter("use_case", event.target.value)}
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

      {!loading && !error && runs.length === 0 && (
        <EmptyState message="No runs yet. Send a request to POST /v1/completions and it'll show up here." />
      )}

      {!loading && !error && runs.length > 0 && (
        <>
          {/* Desktop / tablet: a real table, horizontal scroll only within its own container. */}
          <div className="hidden overflow-x-auto rounded border border-line sm:block">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead className="border-b border-line text-xs text-fog">
                <tr>
                  <th scope="col" className="px-3 py-2 font-normal">
                    Run
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
          <ul className="flex flex-col gap-3 sm:hidden">
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
  return (
    <tr className="border-b border-line last:border-b-0">
      <td className="px-3 py-2 font-mono text-[13px]">
        <Link to={`/runs/${encodeURIComponent(run.run_id)}`} className="text-signal underline decoration-line hover:decoration-signal">
          {shortId(run.run_id)}
        </Link>
      </td>
      <td className="px-3 py-2 font-mono text-[13px] text-fog">{formatTimestamp(run.created_at)}</td>
      <td className="px-3 py-2">{run.use_case ?? <span className="text-fog">-</span>}</td>
      <td className="px-3 py-2">
        <span className="inline-flex items-center gap-2">
          <TierChip tier={run.tier_chosen} />
          {run.escalated && <EscalatedBadge />}
        </span>
      </td>
      <td className="px-3 py-2 font-mono text-[13px]">{run.model_used}</td>
      <td className="px-3 py-2">{run.status}</td>
    </tr>
  );
}

function RunCard({ run }: { run: Run }) {
  return (
    <li className="rounded border border-line bg-panel px-4 py-3">
      <div className="mb-2 flex items-center justify-between">
        <Link
          to={`/runs/${encodeURIComponent(run.run_id)}`}
          className="font-mono text-[13px] text-signal underline decoration-line hover:decoration-signal"
        >
          {shortId(run.run_id)}
        </Link>
        <span className="inline-flex items-center gap-2">
          <TierChip tier={run.tier_chosen} />
          {run.escalated && <EscalatedBadge />}
        </span>
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs text-fog">
        <dt>Created</dt>
        <dd className="font-mono text-signal">{formatTimestamp(run.created_at)}</dd>
        <dt>Use case</dt>
        <dd className="text-signal">{run.use_case ?? "-"}</dd>
        <dt>Model</dt>
        <dd className="font-mono text-signal">{run.model_used}</dd>
        <dt>Status</dt>
        <dd className="text-signal">{run.status}</dd>
      </dl>
    </li>
  );
}
