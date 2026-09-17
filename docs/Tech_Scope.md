# Tech Scope: Task Router

Status: PLAN stage. Sourced from `docs/research/SPRINT-PLAN.md` §3 (stack) and §5 (vertical slices — restated here, not reinvented), cross-checked against `docs/research/task-router-artifact.md` §01–§06 (build order/feature list), `docs/research/otel-replay-options.md` §4 (tracing schema), `docs/research/ollama-local-tier.md` and `docs/research/claude-p-backend.md` (provider mechanics), and `docs/research/REFUTATIONS.md` §B and Minor (gotchas). No product decisions are made here — `docs/Product_Scope.md` already made them; this document is how they get built.

## 1. Stack

| Layer | Choice | Version / detail |
|---|---|---|
| Language / env | Python | 3.12, managed by `uv` |
| API framework | FastAPI | latest stable at build time; one app, no separate services |
| Classifier | scikit-learn | `LogisticRegression` on 8 hand-built features (§2) |
| Storage | SQLite | stdlib `sqlite3`, no ORM |
| Config | PyYAML | `registry.yaml`, `routing.yaml` |
| Tests | pytest | fake provider only — CI never calls Ollama or `claude -p` (SPRINT-PLAN §6 rule 4) |
| Tracing SDK | `opentelemetry-sdk` + `opentelemetry-instrumentation-fastapi` | request-level spans auto-instrumented; classifier/tier/judge spans hand-rolled (otel-replay-options.md §2) |
| Trace storage | Custom `SpanExporter` | ~30-line class writing directly into the SQLite `spans`/`runs` tables (otel-replay-options.md §2(c)) — no collector, no Jaeger dependency for the core deliverable |
| UI | Vite + React + TS | reads the read API (§4); runs/waterfall/replay-diff/stats pages |

Local tier model: `qwen3:1.7b` via Ollama native `/api/chat`, always called with `"think": false` (REFUTATIONS §B.7 — thinking-on-by-default inflates latency/token numbers this project exists to report honestly). Cloud tiers: `claude -p --output-format json --model sonnet|opus` via Python `subprocess`, never `--bare` (claude-p-backend.md §1 — `--bare` drops OAuth and forces API-key billing, which breaks the subscription-only constraint).

Tests never touch a real model. `providers.py` exposes one interface (`send(prompt, model) -> {text, input_tokens, output_tokens, latency, cost, error}`, never raises) with a fake implementation used by every test and by CI. This is stated up front because it governs every slice's test strategy in §5.

## 2. Data model sketch

### registry.yaml

```yaml
models:
  - provider: ollama
    id: qwen3:1.7b
    tier: local
    price_in_per_m: 0.0
    price_out_per_m: 0.0
  - provider: claude_cli
    id: sonnet
    tier: sonnet
    price_in_per_m: 2.0
    price_out_per_m: 10.0
  - provider: claude_cli
    id: opus
    tier: opus
    price_in_per_m: 5.0
    price_out_per_m: 25.0
```
Prices are API list prices, never billed (Product_Scope §4 / §6 D10) — every figure computed from this file must say so next to the number.

### routing.yaml

```yaml
tier_map:
  local: qwen3:1.7b
  sonnet: sonnet
  opus: opus
judge_sample_rate: 1.0        # 1.0 during the battery (S7); dial down after
use_cases:
  extract:      { judge_threshold: 4 }
  reformat:     { judge_threshold: 4 }
  qa_context:   { judge_threshold: 4 }
  summarise:    { judge_threshold: 4 }
  classify:     { judge_threshold: 5 }   # exact-label work
  analyse:      { judge_threshold: 4 }
  reason:       { judge_threshold: 4 }
  create:       { judge_threshold: 3 }   # creative
  judge:        { judge_threshold: 4 }
```
Editable via `PUT /v1/routing-config` (§4) without restarting the service.

### data/prompts.json record shape

```json
{
  "id": "p001",
  "tier": null,
  "use_case": "summarise",
  "prompt": "...",
  "trap": false,
  "notes": ""
}
```
`tier` is null until the operator hand-labels it (Product_Scope §6, Phase A gate). `train.py` and `battery.py` filter to rows where `tier` is non-null — 200 rows get drafted, ~60 get labelled, and running either script over the unlabelled 140 is a bug, not a feature (REFUTATIONS Minor #20).

### The 8 classifier features (`features.py`)

1. length (token or char count)
2. instruction-verb count (imperative verbs present)
3. constraint count (numeric/format constraints stated)
4. supplied-context present (boolean — is reference text attached)
5. output-format specified (boolean/enum)
6. reasoning-word count ("because", "therefore", "step", etc.)
7. question count
8. numeric-token count

All eight are surface features computable without a model call. Per REFUTATIONS §B.14 / Product_Scope §4, these features cannot see meaning — a trap is built to look like an easy prompt on exactly these eight numbers, so the classifier will not catch traps by construction. That is not a bug to fix here; it's why the judge exists (§3).

### SQLite tables

**`runs`** — one row per top-level request. This table does double duty as both the OTel trace root *and* the request/audit record: `run_id` is the OTel `trace_id`, and the same row carries the audit fields (tier, cost inputs, judge outcome) that Product_Scope §3.1 step 4 calls "one record per request." Splitting these into two tables would just require a join on every read for no independence gained — they have the same lifetime and the same primary key.

| Column | Type | Notes |
|---|---|---|
| `run_id` | TEXT PK | OTel trace_id, hex |
| `created_at` | TIMESTAMP | |
| `input_text` | TEXT | original request |
| `input_features` | TEXT (JSON) | classifier output, frozen at run time |
| `tier_chosen` | TEXT | `local` \| `sonnet` \| `opus` |
| `model_used` | TEXT | |
| `output_text` | TEXT | |
| `judge_score` | REAL | null if unjudged (e.g. opus tier, or not sampled) |
| `judge_label` | TEXT | |
| `escalated` | BOOLEAN | default false |
| `escalation_chain` | TEXT (JSON) | array of `{tier, model, reason}` if escalated |
| `status` | TEXT | `ok` \| `error` |
| `total_duration_ms` | INTEGER | |
| `cost_all_tiers` | TEXT (JSON) | what this request would have cost at every tier, per Product_Scope §3.1 step 4 |
| `forced_tier` | TEXT | null on a normal run; set when this run is a replay (otel-replay-options.md §4 design note) |

**`spans`** — one row per span, child of a run; this is the waterfall data.

| Column | Type | Notes |
|---|---|---|
| `span_id` | TEXT PK | OTel span_id, hex |
| `run_id` | TEXT FK → runs | |
| `parent_span_id` | TEXT | null for the root span |
| `name` | TEXT | `router.classify` \| `router.select_tier` \| `chat qwen3:1.7b` \| `router.judge` \| `router.escalate` \| ... |
| `start_ns` | INTEGER | |
| `end_ns` | INTEGER | |
| `attributes` | TEXT (JSON) | `gen_ai.*` + custom attrs, as exported |
| `status` | TEXT | `OK` \| `ERROR` |

**`replays`** — one row per re-run attempt against a stored run.

| Column | Type | Notes |
|---|---|---|
| `replay_id` | TEXT PK | |
| `source_run_id` | TEXT FK → runs | the original request being replayed |
| `forced_tier` | TEXT | tier forced for the replay |
| `new_run_id` | TEXT FK → runs | the new run the replay produced (reuses `runs`/`spans`) |
| `created_at` | TIMESTAMP | |
| `diff_summary` | TEXT (JSON) | precomputed diff: tier/model/output/judge-score deltas |

## 3. Core logic — one worked example

**Synchronous path** (Product_Scope §3.1), traced end to end for a single request:

1. `POST /v1/completions` arrives with `{prompt: "Summarise this email...", use_case: "summarise"}`. FastAPI's auto-instrumentation opens the root span (`run_id` = trace_id).
2. `router.classify` span: `features.py` extracts the 8 features (length=180 chars, verbs=1 "summarise", context=true, ...). No model call. Attribute `router.features` holds the JSON.
3. `router.select_tier` span: the trained `LogisticRegression` scores the feature vector, picks `local`. Attribute `router.tier = "local"`.
4. `chat qwen3:1.7b` span: `providers.py` calls Ollama native `/api/chat` with `"think": false`. Returns text, `input_tokens`, `output_tokens`, latency. `gen_ai.provider.name=ollama`, `gen_ai.request.model=qwen3:1.7b`, `gen_ai.usage.*` set.
5. A row is written to `runs` (`tier_chosen=local`, `model_used=qwen3:1.7b`, `output_text=...`, `cost_all_tiers` computed from `registry.yaml` prices for local/sonnet/opus even though only local was actually called). The response returns to the caller here — nothing below this line blocks the caller (Product_Scope §3.1 step 3).
6. **Background job** (sampled at `judge_sample_rate`): because the answering tier was `local`, the judge is `sonnet` — one tier above, never the same tier grading itself (Product_Scope §3.2, REFUTATIONS §D.15). A `router.judge` span calls `claude -p --model sonnet --output-format json`, asks it to score the local answer 1–5 against the `summarise` use case's threshold (4, from `routing.yaml`). Say it scores 2.
7. Below threshold → `router.escalate`: escalate exactly one tier, local → sonnet (never straight to opus). The sonnet-tier answer replaces `output_text` in the `runs` row; `escalated=true`; `escalation_chain=[{tier: "sonnet", model: "sonnet", reason: "judge_score=2<4"}]`. This escalation becomes a labelled training row for a future `train.py --version 2` (Product_Scope §3.2 last bullet) — it only helps on near-duplicates, it does not teach the classifier to see meaning it wasn't built to see.

**Replay path** (Product_Scope §3.3): `POST /replay {source_run_id: "<the run above>", forced_tier: "opus"}` re-runs steps 2–7 against the same stored `input_text`, but `router.select_tier` is skipped in favor of the forced tier, recorded via an attribute (`router.tier_forced=true`) rather than silently overwritten — the audit trail shows *why* this run took that path. This produces a brand-new `run_id` (so it gets its own waterfall for free) plus one `replays` row linking `source_run_id` → `new_run_id` with a `diff_summary` (tier/model/output/judge-score deltas between the two runs). This is re-run-and-diff against a real historical request, not deterministic replay — LLM calls aren't reproducible byte-for-byte, and the README must say so (otel-replay-options.md §4; SPRINT-PLAN §8).

## 4. API contract

Localhost-only. No auth layer — this runs on one person's own machine against their own subscription (Product_Scope §5 "hosted or public deployment" is explicitly out of scope). The provider interface has a slot for `ANTHROPIC_API_KEY`-based auth for a future hosted variant, but it is not exercised or tested here (SPRINT-PLAN §3, D4).

All error responses share one shape: `{"error": {"code": "...", "message": "...", "details": null}}`.

### POST /v1/completions

Runs the synchronous path (§3).

- **Request body:** `{"prompt": string, "use_case": string, "forced_tier"?: "local"|"sonnet"|"opus"}`. `forced_tier` is optional and exists for internal reuse by the replay path (§4.7) — normal callers omit it.
- **Success (200):** `{"run_id": string, "tier_chosen": string, "model_used": string, "output_text": string, "cost_all_tiers": {"local": number, "sonnet": number, "opus": number}}`
- **Errors:** `422` invalid body (missing `prompt`, unknown `use_case`); `500` if the answering provider call itself errors after retries (the provider interface never raises — it returns an error field — so a 500 here means the router failed to handle that field, which is itself a bug to catch in tests).

### GET /v1/models

Lists the tier registry as currently loaded.

- **Request:** none.
- **Success (200):** `{"models": [{"provider": string, "id": string, "tier": string, "price_in_per_m": number, "price_out_per_m": number}]}`
- **Errors:** none expected (pure read of an in-memory config).

### GET /v1/stats

Aggregate savings, computed both with and without judge tokens counted (Product_Scope §4 — leaving judge cost out overstates the local tier's saving).

- **Request query params:** none required; optional `since` (ISO timestamp) to scope the window.
- **Success (200):** `{"n_requests": int, "by_tier": {"local": int, "sonnet": int, "opus": int}, "saved_pct_excl_judge": number, "saved_pct_incl_judge": number, "price_basis": "api_list_prices_no_money_changed_hands"}`
- **Errors:** `422` on a malformed `since`.

### PUT /v1/routing-config

Edits `routing.yaml` (tier map, per-use-case threshold, `judge_sample_rate`) live, no restart (Product_Scope §3.3).

- **Request body:** full or partial `routing.yaml` shape — `{"tier_map"?: {...}, "use_cases"?: {...}, "judge_sample_rate"?: number}`. Partial update: only provided top-level keys change.
- **Success (200):** the resulting full config, echoed back.
- **Errors:** `422` on an unknown tier name or a threshold outside 1–5; `409` if two `PUT`s race (last-write-wins is not acceptable for a config file — reject the second with `409` and let the caller re-read and retry, since this is a local single-user tool where a lost edit is worse than a rejected one).

### GET /runs

List runs for the dashboard's run list.

- **Request query params:** `page` (default 1), `page_size` (default 20), optional `tier`, `use_case`, `status` filters.
- **Success (200):** `{"data": [{"run_id", "created_at", "tier_chosen", "model_used", "escalated", "status", ...}], "pagination": {"page", "page_size", "total_items", "total_pages"}}`
- **Errors:** `422` on out-of-range pagination params.

### GET /runs/{id}/spans

The waterfall data for one run.

- **Request:** `id` path param (run_id).
- **Success (200):** `{"run": {...full runs row...}, "spans": [{"span_id", "parent_span_id", "name", "start_ns", "end_ns", "attributes", "status"}]}`
- **Errors:** `404` if `run_id` doesn't exist.

### POST /replay

Runs the replay path (§3).

- **Request body:** `{"source_run_id": string, "forced_tier": "local"|"sonnet"|"opus"}`
- **Success (200):** `{"replay_id": string, "new_run_id": string, "diff_summary": {"tier_changed": bool, "model_changed": bool, "judge_score_delta": number|null, "output_changed": bool}}`
- **Errors:** `404` if `source_run_id` doesn't exist; `422` if `forced_tier` isn't one of the three known tiers.

## 5. Vertical slices S0–S8

Restated from SPRINT-PLAN §5 — this table is the task breakdown, not a reinvention of it. Every slice's test strategy runs against the fake provider from §1; nothing here calls a real model or costs money except the one-time smoke test in S0 and the one-time battery in S7 (SPRINT-PLAN §6 rules 3–4).

| # | Slice | Deliverables | Est. | Phase | Test strategy (fake provider) |
|---|---|---|---|---|---|
| S0 | Repo + environment bring-up | `ollama update`; `ollama serve`; `ollama pull qwen3:1.7b`; **5 back-to-back `claude -p --output-format json` calls from a Python subprocess** (Windows stdin risk — claude-p-backend.md §4); one `/api/chat` call asserting `think:false` is actually honored by Ollama's response; a pytest that pins the exact local-tier request body (must include `"think": false`) so a future edit can't silently drop it | 3h | A | The `think:false` pytest is the one real assertion here and it's the point of the slice — it runs against a recorded/pinned request body, not a live model, so it stays in CI |
| S1 | Providers + baseline | `registry.yaml`; `providers.py` `send()` returning text/tokens/latency/cost/error, never raises; fake provider; `baseline.py` (10 prompts × 3 models) | 3h | A | Unit tests on the fake provider assert `send()` never raises even when the fake is configured to simulate an error, and that cost is computed correctly from `registry.yaml` prices |
| S2 | Prompts + classifier | `data/prompts.json` (200 drafted across 9 use cases + 20 traps, `tier: null`), then STOP for labelling; `features.py` (8 features); `train.py` — LogisticRegression on labelled rows only, seeded 25% held-out **and** 5-fold CV, prints n / accuracy ± spread / confusion matrix / per-trap result | 2h | A | Unit tests on `features.py` with hand-built inputs and known expected feature vectors; `train.py` tested against a small synthetic labelled fixture, not the real 60 |
| — | The operator labels ≥60 (1–2h, off the clock) | — | operator | A | — |
| S3 | Synchronous API + tracing | `api.py`: `POST /v1/completions` classify→route→answer→SQLite row; `GET /v1/models`, `GET /v1/stats`, `PUT /v1/routing-config`; OTel from line one (`router.classify`, `router.select_tier`, `chat <model>`); custom SQLite `SpanExporter` → `runs`/`spans`; optional dual Jaeger export | 4h | A | FastAPI `TestClient` against the fake provider end to end; assert the `runs`/`spans` rows land correctly and that span parent/child nesting matches the request tree |
| S4 | Background judge + escalation | Judge = tier above, `judge_sample_rate`; 1–5 JSON score; per-use-case threshold; escalate one tier at a time; swap answer; `forced_tier` param; `replays` table | 3h | B | Fake provider returns a scripted low score to force an escalation path; assert exactly one tier step, never a jump straight to opus, and that `escalation_chain` records the reason |
| S5 | Read API | `GET /runs`, `GET /runs/{id}/spans`, `POST /replay {source_run_id, forced_tier}` | 2h | B | Seed the SQLite fixture with known runs/spans, assert pagination and filter params, assert `POST /replay` produces a `diff_summary` matching a hand-computed expected diff |
| S6 | React UI | List → waterfall → replay-diff → stats (with/without judge tokens; "API list prices, no money changed hands") | 8–10h | B | Component tests against a mocked read API (MSW or equivalent); no live backend required for CI |
| S7 | Battery + retrain | `battery.py` over labelled rows (sample rate 1.0; ≈120–150 real `claude -p` calls, spread over ≥2 five-hour windows); `feedback.py`; `train.py --version 2` on same held-out ids, reported without improvement claims | 3h | B | `battery.py`'s own logic (row filtering, retry/backoff, progress reporting) is unit-tested against the fake provider; the real run happens exactly once, manually triggered, never in CI |
| S8 | README + ADRs | Honest numbers (n, narrowed replay claim, subscription-vs-API-key provider note); 3 ADRs; Jaeger screenshot; committed SQLite fixture so the UI demos with no model running | 2h | B | No new code path — verify the committed fixture actually loads in the UI's dev server as the acceptance check |

**Phase A exit:** S0–S3 green, plus the operator's labels in (Product_Scope §6). **Phase B exit:** S8 done, stop there.

## 6. Gotchas

- **`think:false` is not optional.** `qwen3:1.7b` runs with thinking mode ON by default in Ollama; left on, hidden reasoning tokens inflate the exact latency/cost numbers this project exists to report honestly (Product_Scope §4, REFUTATIONS §B.7). S0 and S1 both pin this in a test so a later refactor can't silently drop the flag.
- **Windows subprocess/stdin for `claude -p`.** Windows had a real, documented stdin bug fixed at v2.1.211 (installed: 2.1.274, so this machine is fine) — but community reports describe further Windows-specific subprocess hangs and console-window spawning. S0's 5-back-to-back-calls smoke test exists specifically to catch this before the full battery depends on it. Use `subprocess.run(..., input=None)` — don't leave an unused stdin pipe attached.
- **Filter `train.py`/`battery.py` to labelled rows only.** 200 prompts get drafted, ~60 get labelled; running either script over the unlabelled 140 null-tier rows is silent corruption, not a feature (REFUTATIONS Minor #20).
- **Judge cost is counted in savings.** A local-tier answer that gets judged by Sonnet still cost one Sonnet call — `GET /v1/stats` reports the saving both with and without judge tokens; neither figure is hidden (Product_Scope §4).
- **Held-out set is ~15 prompts — no v1→v2 improvement claim.** 60 labels × 25% ≈ 15 test items across 3 tiers and 9 use cases; accuracy on 15 items carries roughly a ±20-point spread. `train.py --version 2` reports both models' numbers side by side, never a verdict that v2 is better (Product_Scope §4, REFUTATIONS §D.13).
- **The classifier does not catch traps — the judge does, by design.** The 8 features (§2) are surface-only; a trap is built to look like an easy prompt on exactly those features, so logistic regression structurally cannot learn to flag it. This is stated in the README as a design fact, not hidden as a limitation (Product_Scope §4, REFUTATIONS §D.14).
- **`battery.py` runs once, in Phase B only, subscription only, never `--bare`.** `--bare` skips OAuth/keychain auth and forces `ANTHROPIC_API_KEY` billing, which breaks the "no real money" constraint (Product_Scope §4, claude-p-backend.md §1). The battery is not re-run "to check" — only the held-out subset is re-run if needed (SPRINT-PLAN §6 rule 3).
- **Strip `ANTHROPIC_API_KEY` from the `claude -p` child-process environment.** If that variable happens to be set in the parent shell for any reason, an unmodified `claude` binary will prefer API-key billing over the OAuth/subscription session, silently moving cloud-tier calls onto metered billing. `providers.py`'s subprocess call must explicitly build a child environment with that key absent, not just inherit `os.environ` unchanged.

## Calls made where sources were silent or conflicted

- `runs` doubles as both the OTel trace root and the request/audit record (§2) — Product_Scope §3.1 step 4 calls for "one record per request" separately from the tracing tables in otel-replay-options.md §4, but that source's own `runs` schema already carries every audit field (tier, cost, judge outcome). Keeping them as one table avoids a join with no independence gained; noted explicitly in case a reviewer expects two tables.
- `PUT /v1/routing-config`'s concurrent-write behavior (409 on a race) is not specified anywhere in the source docs — chosen per api-and-interface-design's consistent-error-semantics principle, since a silently lost config edit is worse than a rejected one on a local single-user tool.
- Per-endpoint error codes beyond what SPRINT-PLAN/Product_Scope state (e.g. 404 on unknown `run_id`, 422 on bad pagination) were not in the source docs and were filled in from REST convention per api-and-interface-design.
