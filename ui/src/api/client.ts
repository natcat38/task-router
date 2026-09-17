import type {
  ApiErrorBody,
  ModelsResponse,
  ReplayRequestBody,
  ReplayResponse,
  RunSpansResponse,
  RunsListParams,
  RunsListResponse,
  StatsResponse,
} from "./types";

/**
 * Base URL for the router API. Vite exposes `import.meta.env.VITE_API_BASE`
 * at build time; default to the router's own default bind address
 * (Tech_Scope §4: "Localhost-only") so the UI works against a freshly
 * cloned backend with zero configuration.
 */
export const API_BASE: string =
  (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://localhost:8000";

/** Thrown for any non-2xx response. Carries the parsed `{error: {...}}`
 * body from Tech_Scope §4 when the server sent one, so callers can show
 * the router's own message rather than a generic "request failed." */
export class ApiError extends Error {
  status: number;
  code?: string;

  constructor(status: number, message: string, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    // Network-level failure (server not running, DNS, CORS) -- distinct
    // from an HTTP error status, but the UI's error states treat both the
    // same way (Design_Direction.md "Couldn't reach the router API...").
    throw new ApiError(0, `Could not reach ${API_BASE}${path}`);
  }

  if (!response.ok) {
    let body: ApiErrorBody | undefined;
    try {
      body = (await response.json()) as ApiErrorBody;
    } catch {
      // Response wasn't JSON -- fall through with a generic message.
    }
    throw new ApiError(
      response.status,
      body?.error?.message ?? `Request failed with status ${response.status}`,
      body?.error?.code,
    );
  }

  return (await response.json()) as T;
}

function buildQuery(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) search.set(key, String(value));
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

/** GET /runs -- Tech_Scope §4. */
export function getRuns(params: RunsListParams = {}): Promise<RunsListResponse> {
  const query = buildQuery({
    page: params.page,
    page_size: params.page_size,
    tier: params.tier,
    use_case: params.use_case,
    status: params.status,
  });
  return request<RunsListResponse>(`/runs${query}`);
}

/** GET /runs/{id}/spans -- Tech_Scope §4. */
export function getRunSpans(runId: string): Promise<RunSpansResponse> {
  return request<RunSpansResponse>(`/runs/${encodeURIComponent(runId)}/spans`);
}

/** POST /replay -- Tech_Scope §4. */
export function postReplay(body: ReplayRequestBody): Promise<ReplayResponse> {
  return request<ReplayResponse>("/replay", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** GET /v1/stats -- Tech_Scope §4. `since` is an optional ISO timestamp. */
export function getStats(since?: string): Promise<StatsResponse> {
  const query = buildQuery({ since });
  return request<StatsResponse>(`/v1/stats${query}`);
}

/** GET /v1/models -- Tech_Scope §4. */
export function getModels(): Promise<ModelsResponse> {
  return request<ModelsResponse>("/v1/models");
}
