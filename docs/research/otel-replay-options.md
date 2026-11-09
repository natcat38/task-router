# OTel + Replay Debugger — Options for a 2.5-Day Build

Research date: 2026-09-17. Scope: LLM task router (FastAPI, classifier → tier choice → model call → async judge → escalation) needs a trace-based "replay debugger": timeline UI + re-run a stored request against a different tier.

---

## 1. OpenTelemetry GenAI semantic conventions — current status

**Not stable. Everything is "Development" stability (the status formerly called "experimental").** As of the conventions' move in v1.42.0 (12 June 2026), all `gen_ai.*` attributes were relocated out of the core `semantic-conventions` repo into a dedicated repo, `open-telemetry/semantic-conventions-genai`, specifically so this area can keep changing without being held to the core spec's stability bar. That new repo has no tagged releases yet and no finalized schema URL to pin against — you follow a commit or a framework release, not a version. ([opentelemetry.io blog](https://opentelemetry.io/blog/2026/genai-observability/), [DEV: "NOT stable yet"](https://dev.to/azena-ai/opentelemetrys-genai-semantic-conventions-are-not-stable-yet-heres-what-actually-shipped-in-2026-3mke), [opentelemetry.io gen-ai attribute registry](https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/))

**Practical implication for a portfolio project:** treat these attribute names as a *convention to imitate*, not a contract to depend on. Don't build validation or a schema check against them. Pin the instrumentation library version you use and don't auto-upgrade mid-sprint.

**Key attributes** (current names; several older names are now marked deprecated in favor of these — noted where relevant):

| Attribute | Type | Notes |
|---|---|---|
| `gen_ai.provider.name` | string | Replaces the older `gen_ai.system` (e.g. `openai`, `anthropic`, `ollama`). If you copied code samples from 2024–2025 you will see `gen_ai.system` — that name is deprecated. |
| `gen_ai.operation.name` | string | `chat`, `embeddings`, `text_completion`, `generate_content`, `execute_tool`, etc. |
| `gen_ai.request.model` | string | Model requested, e.g. `llama3:8b`, `claude-sonnet-5`. |
| `gen_ai.response.model` | string | Model that actually served the response. |
| `gen_ai.usage.input_tokens` | int | Replaces `gen_ai.usage.prompt_tokens`. |
| `gen_ai.usage.output_tokens` | int | Replaces `gen_ai.usage.completion_tokens`. |
| `gen_ai.usage.cache_creation.input_tokens` / `cache_read.input_tokens` | int | Prompt-cache accounting (relevant if you cache classifier prompts). |
| `gen_ai.request.temperature`, `top_k`, `top_p`, `max_tokens`, `stream` | — | Request configuration. |
| `gen_ai.input.messages` / `gen_ai.output.messages` | structured | Full prompt/response payloads — now routed through these attributes/the Events API rather than the old flat `gen_ai.prompt` / `gen_ai.completion` strings. Treat as opt-in (can be large / hold PII). |
| `gen_ai.tool.name`, `gen_ai.tool.call.id`, `gen_ai.tool.definitions` | — | Useful for your escalation/tool-call steps if you model escalation as a tool call. |
| `gen_ai.conversation.id` | string | Good fit for your `request_id`/trace grouping if you want cross-span correlation beyond trace_id. |
| `gen_ai.evaluation.name`, `gen_ai.evaluation.score.value`, `gen_ai.evaluation.score.label` | — | **This is the closest official fit for your judge span** — emit the judge's score/verdict as an evaluation attribute (or a child span) rather than inventing a custom namespace. |

**Span naming convention:** the general pattern the spec recommends is `{gen_ai.operation.name} {gen_ai.request.model}` for a request span, e.g. `chat llama3:8b`, and `execute_tool {gen_ai.tool.name}` for tool spans. I could not pull the exact current wording from the new `semantic-conventions-genai` repo's rendered docs (GitHub's page render didn't expose the markdown body to the fetch), so treat this naming pattern as "likely correct, verify against `docs/gen-ai/gen-ai-spans.md` in that repo before you lock in span names." For your own custom spans (classifier, tier-choice, judge) you're outside the GenAI conventions anyway — name them plainly: `router.classify`, `router.select_tier`, `router.judge`, `router.escalate`.

Sources: [opentelemetry.io — Inside the LLM Call: GenAI Observability with OpenTelemetry](https://opentelemetry.io/blog/2026/genai-observability/), [opentelemetry.io — Gen AI attribute registry](https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/), [github.com/open-telemetry/semantic-conventions-genai](https://github.com/open-telemetry/semantic-conventions-genai), [Dash0 — GenAI Semantic Conventions Explained](https://www.dash0.com/knowledge/opentelemetry-genai-semantic-conventions-explained)

---

## 2. Python emission in FastAPI

**Base packages:** `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-instrumentation-fastapi`, plus one exporter package (`opentelemetry-exporter-otlp-proto-http` or `-grpc`).

**Auto-instrumentation (request-level spans, ~10 lines):**
```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

trace.set_tracer_provider(TracerProvider())
trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint="http://localhost:4318/v1/traces"))
)
FastAPIInstrumentor().instrument_app(app)  # wraps every route in a span automatically
```
This alone gives you one span per HTTP request with route, status code, duration — not your classifier/tier/judge internals.

**Custom spans for classifier/route/judge (a few lines each):**
```python
tracer = trace.get_tracer("router")

with tracer.start_as_current_span("router.classify") as span:
    features = classify(request_text)
    span.set_attribute("router.features", json.dumps(features))

with tracer.start_as_current_span("router.select_tier") as span:
    tier = choose_tier(features)
    span.set_attribute("router.tier", tier)

with tracer.start_as_current_span(f"chat {model_name}") as span:
    span.set_attribute("gen_ai.provider.name", "ollama" if tier == "local" else "anthropic")
    span.set_attribute("gen_ai.request.model", model_name)
    result = call_model(model_name, prompt)
    span.set_attribute("gen_ai.usage.input_tokens", result.input_tokens)
    span.set_attribute("gen_ai.usage.output_tokens", result.output_tokens)

with tracer.start_as_current_span("router.judge") as span:
    verdict = judge(result)
    span.set_attribute("gen_ai.evaluation.score.value", verdict.score)
    span.set_attribute("gen_ai.evaluation.score.label", verdict.label)
    if verdict.escalate:
        span.add_event("router.escalation_triggered", {"reason": verdict.reason})
```
Nesting these under the auto-instrumented request span gives you the exact parent/child tree a timeline UI needs, for free, via context propagation — no manual span-ID plumbing required as long as they're created inside the request handler's async context.

Sources: [opentelemetry-python-contrib — FastAPI instrumentation docs](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/fastapi/fastapi.html), [Real Python — Integrate OpenTelemetry with FastAPI](https://realpython.com/fastapi-opentelemetry/), [SigNoz — OpenTelemetry FastAPI practical guide](https://signoz.io/blog/opentelemetry-fastapi/)

**Exporters — three options:**

**(a) OTLP to a local collector or directly to a backend.** As above — `OTLPSpanExporter(endpoint=...)`, HTTP or gRPC. This is what Jaeger, Tempo, Langfuse, and Phoenix all speak natively, so it's the one exporter you should actually build, regardless of which viewer you pick.

**(b) Console/file exporter.** `ConsoleSpanExporter()` for stdout, or pipe to a file — zero setup, useful for debugging your own instrumentation before a viewer exists, not a deliverable.

**(c) Custom `SpanExporter` writing directly into SQLite/Postgres.** This is genuinely small. The SDK's `SpanExporter` interface has one method you must implement, `export(spans) -> SpanExportResult`, plus optional `shutdown()`/`force_flush()`. A minimal SQLite version is roughly **25–40 lines**:
```python
import sqlite3, json
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

class SQLiteSpanExporter(SpanExporter):
    def __init__(self, db_path):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("""CREATE TABLE IF NOT EXISTS spans (
            trace_id TEXT, span_id TEXT, parent_span_id TEXT,
            name TEXT, start_ns INTEGER, end_ns INTEGER,
            attributes TEXT, status TEXT)""")

    def export(self, spans):
        for s in spans:
            ctx = s.get_span_context()
            self.conn.execute(
                "INSERT INTO spans VALUES (?,?,?,?,?,?,?,?)",
                (format(ctx.trace_id, "032x"), format(ctx.span_id, "016x"),
                 format(s.parent.span_id, "016x") if s.parent else None,
                 s.name, s.start_time, s.end_time,
                 json.dumps(dict(s.attributes)), s.status.status_code.name))
        self.conn.commit()
        return SpanExportResult.SUCCESS

    def shutdown(self): self.conn.close()
```
There's already a reference implementation for the same idea (`wperron/sqliteexporter`) you can crib from instead of writing from scratch. Wire it in with `add_span_processor(BatchSpanProcessor(SQLiteSpanExporter("traces.db")))` alongside — or instead of — the OTLP one; nothing stops you exporting to both an OTLP collector *and* your own DB simultaneously, which is actually the cheapest way to get both a "real OTel" story and full control over replay data (see §4).

Sources: [opentelemetry-python.readthedocs.io — SDK trace.export](https://opentelemetry-python.readthedocs.io/en/latest/sdk/trace.export.html), [opentelemetry.io — Python exporters](https://opentelemetry.io/docs/languages/python/exporters/), [github.com/wperron/sqliteexporter](https://github.com/wperron/sqliteexporter)

---

## 3. Viewer options, ranked by build time

| Option | Setup time | What it shows | Satisfies "replay"? |
|---|---|---|---|
| **(a) Jaeger all-in-one, Docker** | ~15 min | One `docker run` (image `jaegertracing/all-in-one`, ports 16686 UI / 4317+4318 OTLP), point your `OTLPSpanExporter` at it, done. Full span tree, timing waterfall, tag search. In-memory storage by default (lost on restart unless you add a backend). | **No.** Pure viewer — no re-run, no diffing, no data model for "try this request again on a different tier." |
| **(b) Grafana Tempo (+Grafana)** | ~30–45 min | Docker-compose with Tempo + Grafana; trace search via TraceQL, trace waterfall view in Grafana's Trace View panel. More production-flavored than Jaeger, more moving parts (needs object storage config even for local, plus wiring Grafana as the query UI). | **No.** Same ceiling as Jaeger — a viewer, not a replay tool. Not worth the extra setup time over Jaeger for a 2.5-day scope. |
| **(c) Langfuse self-host** | ~1–2 hrs (docker-compose stack: Postgres, ClickHouse, Redis, Langfuse server/worker) | Has a native OTLP endpoint (`/api/public/otel`) and explicitly maps `gen_ai.*` GenAI-convention spans into its "generation" object model (model, tokens, cost) with other spans nested as regular observations. Has a **Playground** that lets you take a captured generation, edit the prompt/params, and re-run it against a model. | **Partially.** The Playground re-run is prompt-level, not "replay this exact router decision tree" — but it is a real, already-built re-run UI, which is more than (a)/(b) give you. Heavier infra than your 2.5-day budget probably wants for a router side-project (ClickHouse alone is a lot of Docker Desktop RAM on a laptop). |
| **(c) Arize Phoenix self-host** | ~20–30 min (single container or docker-compose w/ Postgres for persistence) | OTLP-native (HTTP :6006, gRPC :4317) via OpenInference instrumentation, which is compatible with but not identical to the GenAI semconv names — expect to map a few attributes. Full trace tree (retrieval/prompt/tool/model steps). Has a **Playground** for prompt replay/comparison across models. | **Partially**, same shape as Langfuse: re-run is "take this prompt and try other model params," not "re-execute the whole router pipeline." Lighter to stand up than Langfuse and closer to your token budget. |
| **(d) Custom React timeline reading from Postgres/SQLite via a small API** | ~4–8 hrs | Whatever you build: waterfall/tree view of spans for one `trace_id`, attribute inspector per span, and — critically — **a "re-run" button that's real**, because you own the data model and the execution path. | **Yes, fully**, and it's the only option where "re-run stored request against tier X and diff outputs" is a first-class feature rather than a side effect of a prompt playground. |

**Reading this table honestly for a hiring-manager portfolio piece:** (a)/(b) cost little time but can't do the one thing the project is named for. (c) tools do "replay" in the prompt-playground sense but that's a materially different claim than "replay this agent run" — a reviewer who's used Langfuse or Phoenix will notice the gap between "we re-ran a prompt" and "we re-ran the router's tier decision," so don't oversell it if you go this route. (d) is the only option that matches the brief exactly, and it's also the only one that produces something visibly *yours* in a portfolio review rather than "I stood up an open-source tool."

Sources: [Jaeger — Getting Started (v1.76)](https://www.jaegertracing.io/docs/1.76/getting-started/), [Grafana Tempo — Quick start (Docker example)](https://grafana.com/docs/tempo/latest/docker-example/), [Langfuse — OpenTelemetry (OTEL) for LLM Observability](https://langfuse.com/integrations/native/opentelemetry), [Langfuse — Observability via OpenTelemetry (self-host config)](https://langfuse.com/self-hosting/configuration/observability), [Arize Phoenix — GitHub](https://github.com/Arize-ai/phoenix), [Arize — Phoenix product page](https://arize.com/phoenix/)

---

## 4. What "replay" honestly means in a 2.5-day scope

**Deterministic re-execution — the request replays byte-for-byte identically, including the classifier's exact feature extraction and any non-determinism in the model call — is not achievable in 2.5 days**, and arguably not desirable: LLM calls aren't deterministic even at temperature 0 across provider versions, and Ollama model weights/versions can drift under you. Don't build toward this; don't claim it.

**What's actually buildable and still an honest, useful claim: "take a stored request (exact input + exact feature snapshot + exact tier decision that was made), and (1) show it back exactly as it ran, and (2) let the user re-run the same input through the pipeline forcing a different tier, then diff the two runs' outputs side by side."** That is a real, demoable feature, it directly exercises your router's tier-switching logic (which is presumably the actual point of the project), and it's honest about not being deterministic replay — it's "re-run and compare," which is what every one of the OSS tools above actually does too under the "replay" marketing term.

**Minimal data model** (works for both SQLite and Postgres; this is the schema your custom exporter in §2(c) should target, and it's also what a custom React timeline in §3(d) reads from):

```sql
-- One row per top-level request (aka a "trace")
CREATE TABLE runs (
    run_id           TEXT PRIMARY KEY,      -- = OTel trace_id, hex
    created_at       TIMESTAMP NOT NULL,
    input_text       TEXT NOT NULL,         -- the original request payload
    input_features   TEXT,                  -- JSON: classifier output, frozen at run time
    tier_chosen      TEXT NOT NULL,         -- 'local' | 'claude' | etc.
    model_used       TEXT NOT NULL,
    output_text      TEXT,
    judge_score      REAL,
    judge_label      TEXT,
    escalated        BOOLEAN DEFAULT FALSE,
    escalation_chain TEXT,                  -- JSON array of {tier, model, reason} if escalated more than once
    status            TEXT,                 -- 'ok' | 'error'
    total_duration_ms INTEGER
);

-- One row per span, child of a run — this is your timeline/waterfall data
CREATE TABLE spans (
    span_id          TEXT PRIMARY KEY,      -- OTel span_id, hex
    run_id           TEXT NOT NULL REFERENCES runs(run_id),
    parent_span_id   TEXT,                  -- NULL for the root span
    name             TEXT NOT NULL,         -- 'router.classify' | 'chat llama3:8b' | 'router.judge' | ...
    start_ns         INTEGER NOT NULL,
    end_ns            INTEGER NOT NULL,
    attributes       TEXT,                  -- JSON blob: gen_ai.* + custom attrs, as exported
    status           TEXT                   -- 'OK' | 'ERROR'
);

-- One row per re-run attempt against a stored run
CREATE TABLE replays (
    replay_id        TEXT PRIMARY KEY,
    source_run_id    TEXT NOT NULL REFERENCES runs(run_id),  -- the original request being replayed
    forced_tier      TEXT NOT NULL,          -- tier the user chose to replay against
    new_run_id       TEXT NOT NULL REFERENCES runs(run_id),  -- the new run produced by the replay (reuses runs+spans tables)
    created_at       TIMESTAMP NOT NULL,
    diff_summary     TEXT                    -- optional: precomputed diff (token count delta, judge score delta, text diff)
);
```

Design notes:
- `runs` + `spans` is literally the OTel data model (trace + spans) simplified to exactly what your UI needs — you don't need OTel's full attribute/event/link richness for a portfolio project.
- A "replay" is just a normal `run` (so it gets its own timeline for free) plus one row in `replays` linking it back to the original and recording what was forced. The diff view in the UI is just "load `source_run_id` and `new_run_id`, show both timelines side by side, highlight `tier_chosen`, `model_used`, `output_text`, `judge_score` differences."
- To force a tier on replay, your router needs one code path change: an optional `forced_tier` parameter that, when present, skips the tier-selection span's normal logic and records *why* it took that path (attribute `router.tier_forced = true`) — cheap to add now, saves you from a rewrite later.

---

## 5. Prior art to borrow from (links only)

- [traceloop/openllmetry](https://github.com/traceloop/openllmetry) — OTel-native LLM instrumentation, Apache 2.0; look at how it structures span attributes per-provider.
- [Traceloop docs — OpenLLMetry + Laminar integration](https://www.traceloop.com/docs/openllmetry/integrations/laminar) — shows how a second-party UI consumes OpenLLMetry-shaped spans.
- [Laminar (laminar.sh)](https://laminar.sh/) — open-source, OTel-native agent observability UI; look at its timeline/waterfall component for layout ideas.
- [Arize-ai/phoenix](https://github.com/Arize-ai/phoenix) — full source for a self-hosted OTel trace UI + Playground re-run feature; useful as a reference implementation even if you don't deploy it.
- [CSOAI-ORG/awesome-agentops-landscape](https://github.com/CSOAI-ORG/awesome-agentops-landscape) — curated list of AgentOps/observability tools (AgentOps, LangSmith, etc.) with feature comparisons, useful for scanning UI screenshots/READMEs quickly without individually visiting each project.
- LangSmith (langchain's hosted trace UI) has no self-serve OSS repo, but its public docs/marketing pages have UI screenshots worth studying for timeline/step-detail layout conventions — check `docs.smith.langchain.com` directly rather than a repo.

---

## 6. Recommendation

**Cheapest stack that still shows "OpenTelemetry" and a real replay UI:**

1. Instrument the FastAPI router with `opentelemetry-sdk` + `opentelemetry-instrumentation-fastapi`, using `gen_ai.*` attribute names on the model-call span and plain custom spans (`router.classify`, `router.select_tier`, `router.judge`) elsewhere. — **~2 hrs**
2. Write the ~30-line custom `SpanExporter` from §2(c) that writes directly into SQLite using the `runs`/`spans`/`replays` schema from §4 — this *is* your storage layer, no separate collector needed. — **~1.5 hrs**
3. Build a small FastAPI (or reuse the router's own app) read API: `GET /runs`, `GET /runs/{id}/spans`, `POST /replay` (takes `source_run_id` + `forced_tier`, re-invokes the pipeline, returns `new_run_id`). — **~3 hrs**
4. Build the React timeline: run list, waterfall view for one run's spans (span name + duration bar + click-to-expand attributes), and a side-by-side diff view for a replay pair. — **~8–10 hrs**
5. Optionally also run Jaeger all-in-one via `docker run jaegertracing/all-in-one` pointed at the same OTLP exporter (dual-export, per §2), purely so you can screenshot "spans in Jaeger" as evidence of real OTel compliance alongside your own UI — costs almost nothing since the SDK setup is shared. — **~20 min**

Total: **roughly 15–17 hours of the 2.5-day (≈20-hour) budget**, leaving slack for judge-escalation logic, styling, and a README that's honest about what "replay" means here (re-run-and-diff, not deterministic replay) — which matters more to a hiring manager who's actually used one of these tools than an inflated claim would.
