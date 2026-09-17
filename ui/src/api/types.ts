/**
 * Types for the router's read API, matching docs/Tech_Scope.md §4 exactly
 * and cross-checked against the live implementation in api.py + the
 * `runs`/`spans` schema in src/task_router/db.py. Field names mirror the
 * JSON on the wire (snake_case) rather than being renamed to camelCase, so
 * a reader comparing this file to the API contract doesn't have to
 * translate.
 */

export type Tier = "local" | "sonnet" | "opus";

export type RunStatus = "ok" | "error";

/** One entry from `registry.yaml`, as returned by GET /v1/models. */
export interface ModelEntry {
  provider: string;
  id: string;
  tier: string;
  price_in_per_m: number;
  price_out_per_m: number;
}

export interface ModelsResponse {
  models: ModelEntry[];
}

/** What a request would have cost at each tier (Tech_Scope §2 `cost_all_tiers`). */
export type CostAllTiers = Record<Tier, number | null>;

/** One step of an escalation (Tech_Scope §2 `escalation_chain`). */
export interface EscalationStep {
  tier: string;
  model: string;
  reason: string;
}

/**
 * A full `runs` row, as returned by both GET /runs (list) and
 * GET /runs/{id}/spans (`run` field) -- api.py's `_run_row_to_dict` uses
 * one shape for both, so this type does too.
 */
export interface Run {
  run_id: string;
  created_at: string;
  input_text: string;
  input_features: Record<string, number> | null;
  use_case: string | null;
  tier_chosen: Tier;
  model_used: string;
  output_text: string | null;
  judge_score: number | null;
  judge_label: string | null;
  escalated: boolean;
  escalation_chain: EscalationStep[] | null;
  status: RunStatus;
  total_duration_ms: number | null;
  cost_all_tiers: CostAllTiers | null;
  forced_tier: Tier | null;
  judge_cost: number;
}

export interface Pagination {
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
}

export interface RunsListResponse {
  data: Run[];
  pagination: Pagination;
}

export interface RunsListParams {
  page?: number;
  page_size?: number;
  tier?: Tier;
  use_case?: string;
  status?: RunStatus;
}

/** One row from the `spans` table (Tech_Scope §2) -- the waterfall data. */
export interface Span {
  span_id: string;
  run_id: string;
  parent_span_id: string | null;
  name: string;
  start_ns: number;
  end_ns: number;
  attributes: Record<string, unknown>;
  status: "OK" | "ERROR" | null;
}

export interface RunSpansResponse {
  run: Run;
  spans: Span[];
}

export interface ReplayRequestBody {
  source_run_id: string;
  forced_tier: Tier;
}

export interface DiffSummary {
  tier_changed: boolean;
  model_changed: boolean;
  judge_score_delta: number | null;
  output_changed: boolean;
}

export interface ReplayResponse {
  replay_id: string;
  new_run_id: string;
  diff_summary: DiffSummary;
}

export interface StatsResponse {
  n_requests: number;
  by_tier: Record<Tier, number>;
  saved_pct_excl_judge: number;
  saved_pct_incl_judge: number;
  price_basis: string;
}

/** The `{"error": {"code", "message", "details"}}` shape every endpoint
 * shares on failure (Tech_Scope §4). */
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details: unknown;
  };
}
