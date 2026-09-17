"""FastAPI app: the synchronous request lifecycle (Tech_Scope.md §4) --
`POST /v1/completions` (classify -> route -> answer -> audit row + spans),
`GET /v1/models`, `GET /v1/stats`, `PUT /v1/routing-config`.

S4 adds the background judge + escalation (Tech_Scope §5 S4 row,
Product_Scope §3.2): `POST /v1/completions` schedules
`task_router.judge.judge_and_escalate` as a FastAPI `BackgroundTask` after a
successful answer, so it always runs strictly after the response has gone
back to the caller -- the caller never waits on it. `GET /v1/stats` now
folds judge-call cost into `saved_pct_incl_judge`.

S5 adds the read API (`GET /runs`, `GET /runs/{id}/spans`) and replay
(`POST /replay`). The classify -> select_tier -> answer -> persist pipeline
that `POST /v1/completions` runs is factored out into `_run_pipeline()` so
`POST /replay` can reuse it verbatim with `forced_tier` set, per ADR 0002:
replay re-runs the *entire* router pipeline (classify still runs and is
visible, even though its output is overridden) against the source run's
stored `input_text`/`use_case`, producing a brand-new run_id/spans rather
than mutating the original. Replay is non-deterministic (model outputs vary
call to call), so the new run is always a separate row, never presented as
a corrected version of the source run (ADR 0002's "Consequences"). Unlike
`POST /v1/completions`, `POST /replay` runs the judge/escalate step
*synchronously* (not as a background task) so the response's `diff_summary`
can include the replay's final judge score -- the user is explicitly
waiting on this call, unlike the latency-sensitive completions path.

`create_app()` is a factory, not a module-level singleton, so tests can
build an isolated instance against a temp SQLite file, a fake provider, and
a stub classifier (module seams -- Tech_Scope §5 S3 test strategy) without
ever touching Ollama or `claude -p`. `app = create_app()` at the bottom is
the default instance `uvicorn api:app` serves.
"""

from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from fastapi import BackgroundTasks, FastAPI
from fastapi.responses import JSONResponse
from opentelemetry import trace as trace_api
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.trace import Status, StatusCode
from pydantic import BaseModel, field_validator

from task_router import classifier as classifier_module
from task_router import db as db_module
from task_router import judge as judge_module
from task_router import routing_config as routing_config_module
from task_router import tracing as tracing_module
from task_router.features import extract_features
from task_router.providers import send as default_send
from task_router.registry import load_registry

SendFn = Callable[..., dict]
SelectTierFn = Callable[[dict], str]

KNOWN_TIERS = ("local", "sonnet", "opus")


class CompletionRequest(BaseModel):
    prompt: str
    use_case: str
    forced_tier: Optional[str] = None

    @field_validator("forced_tier")
    @classmethod
    def _forced_tier_is_known(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in KNOWN_TIERS:
            raise ValueError(f"forced_tier must be one of {KNOWN_TIERS}")
        return v


class RoutingConfigUpdate(BaseModel):
    tier_map: Optional[dict] = None
    use_cases: Optional[dict] = None
    judge_sample_rate: Optional[float] = None


class ReplayRequest(BaseModel):
    source_run_id: str
    forced_tier: str

    @field_validator("forced_tier")
    @classmethod
    def _forced_tier_is_known(cls, v: str) -> str:
        if v not in KNOWN_TIERS:
            raise ValueError(f"forced_tier must be one of {KNOWN_TIERS}")
        return v


def _error(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message, "details": None}}


def _run_row_to_dict(row) -> dict:
    """A `runs` row as JSON-shaped output: JSON text columns parsed back
    into objects, `escalated` as a real bool. Used by GET /runs and
    GET /runs/{id}/spans -- both read the same row shape (Tech_Scope §4)."""
    d = dict(row)
    d["input_features"] = json.loads(d["input_features"]) if d.get("input_features") else None
    d["cost_all_tiers"] = json.loads(d["cost_all_tiers"]) if d.get("cost_all_tiers") else None
    d["escalation_chain"] = json.loads(d["escalation_chain"]) if d.get("escalation_chain") else None
    d["escalated"] = bool(d["escalated"])
    return d


def _span_row_to_dict(row) -> dict:
    d = dict(row)
    d["attributes"] = json.loads(d["attributes"]) if d.get("attributes") else {}
    return d


def _compute_diff(source_row, new_row) -> dict:
    """diff_summary between a source run and its replay (Tech_Scope §4 /
    ADR 0002) -- compared on the FINAL persisted tier/model/output/score of
    each row, i.e. after that row's own judge/escalate has already run, so
    an escalation on either side is reflected in the diff rather than
    hidden behind the pre-escalation tier."""
    source_score = source_row["judge_score"]
    new_score = new_row["judge_score"]
    return {
        "tier_changed": source_row["tier_chosen"] != new_row["tier_chosen"],
        "model_changed": source_row["model_used"] != new_row["model_used"],
        "judge_score_delta": (
            new_score - source_score if source_score is not None and new_score is not None else None
        ),
        "output_changed": source_row["output_text"] != new_row["output_text"],
    }


def create_app(
    *,
    db_path: Optional[Path] = None,
    send_fn: Optional[SendFn] = None,
    select_tier_fn: Optional[SelectTierFn] = None,
    routing_config_path: Optional[Path] = None,
) -> FastAPI:
    conn = db_module.get_connection(db_path)
    send = send_fn or default_send
    select_tier = select_tier_fn or classifier_module.select_tier
    tracer, provider = tracing_module.setup_tracing(conn)

    app = FastAPI(title="task-router")
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)

    def _run_pipeline(
        *,
        prompt: str,
        use_case: str,
        forced_tier: Optional[str],
        background_tasks: Optional[BackgroundTasks],
        synchronous_judge: bool = False,
    ) -> dict:
        """classify -> select_tier -> answer -> persist, shared by
        POST /v1/completions and POST /replay (ADR 0002: replay re-runs
        this whole pipeline with `forced_tier` overriding select_tier's
        output, not a span/model swap on the stored prompt). Returns a dict
        with an internal `_status` key (200 or 500) the caller strips
        before sending the HTTP response.

        `synchronous_judge=True` (used by /replay) calls
        `judge_and_escalate` in-line instead of scheduling it as a
        background task, so the caller can read back the run's final
        judge/escalation outcome immediately -- needed for the replay
        diff. `POST /v1/completions` keeps the async path so its caller
        never waits on the judge (Product_Scope §3.2).
        """
        # Captured now, while the FastAPI-instrumented request span is still
        # the ambient "current" span, so the judge job -- whether run inline
        # or as a background task outside that ambient context (see
        # judge.py) -- can explicitly re-parent its spans under the same
        # request root instead of becoming an unparented span of its own.
        root_span_context = trace_api.get_current_span().get_span_context()

        with tracer.start_as_current_span("router.classify") as classify_span:
            features = extract_features(prompt)
            classify_span.set_attribute("router.features", json.dumps(features))
            run_id = format(classify_span.get_span_context().trace_id, "032x")

        with tracer.start_as_current_span("router.select_tier") as tier_span:
            if forced_tier is not None:
                tier = forced_tier
                tier_span.set_attribute("router.tier_forced", True)
            else:
                tier = select_tier(features)
            tier_span.set_attribute("router.tier", tier)

        registry = load_registry()
        model_entry = registry.by_tier(tier)

        with tracer.start_as_current_span(f"chat {model_entry.id}") as chat_span:
            provider_name = "ollama" if model_entry.provider == "ollama" else "anthropic"
            chat_span.set_attribute("gen_ai.provider.name", provider_name)
            chat_span.set_attribute("gen_ai.request.model", model_entry.id)
            result = send(prompt, model_entry.id)
            chat_span.set_attribute("gen_ai.usage.input_tokens", result["input_tokens"])
            chat_span.set_attribute("gen_ai.usage.output_tokens", result["output_tokens"])
            if result["error"]:
                chat_span.set_status(Status(StatusCode.ERROR, result["error"]))

        status = "error" if result["error"] else "ok"

        cost_all_tiers: dict[str, Optional[float]] = {}
        for t in KNOWN_TIERS:
            entry = registry.by_tier(t)
            cost_all_tiers[t] = registry.cost(
                entry.id, result["input_tokens"], result["output_tokens"]
            )

        conn.execute(
            "INSERT INTO runs (run_id, created_at, input_text, input_features, "
            "use_case, tier_chosen, model_used, output_text, status, "
            "total_duration_ms, cost_all_tiers, forced_tier) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                run_id,
                datetime.now(timezone.utc).isoformat(),
                prompt,
                json.dumps(features),
                use_case,
                tier,
                model_entry.id,
                result["text"],
                status,
                None,
                json.dumps(cost_all_tiers),
                forced_tier,
            ),
        )
        conn.commit()

        if result["error"]:
            return {"_status": 500, "run_id": run_id, "error": result["error"]}

        judge_kwargs = dict(
            conn=conn,
            tracer=tracer,
            parent_span_context=root_span_context,
            send_fn=send,
            registry=registry,
            routing_config_path=routing_config_path,
            run_id=run_id,
            prompt=prompt,
            use_case=use_case,
            tier_chosen=tier,
            model_id=model_entry.id,
            output_text=result["text"],
        )
        if synchronous_judge:
            judge_module.judge_and_escalate(**judge_kwargs)
        else:
            # S4 safety net: judge + escalate strictly after the response
            # below has gone back to the caller (Product_Scope §3.2) --
            # scheduled here, run by Starlette after this handler returns.
            assert background_tasks is not None
            background_tasks.add_task(judge_module.judge_and_escalate, **judge_kwargs)

        return {
            "_status": 200,
            "run_id": run_id,
            "tier_chosen": tier,
            "model_used": model_entry.id,
            "output_text": result["text"],
            "cost_all_tiers": cost_all_tiers,
        }

    @app.post("/v1/completions")
    def post_completions(body: CompletionRequest, background_tasks: BackgroundTasks):
        try:
            known_use_cases = routing_config_module.load_config(
                routing_config_path
            ).get("use_cases", {})
        except FileNotFoundError:
            known_use_cases = {}
        if known_use_cases and body.use_case not in known_use_cases:
            return JSONResponse(
                status_code=422,
                content=_error("unknown_use_case", f"unknown use_case {body.use_case!r}"),
            )

        outcome = _run_pipeline(
            prompt=body.prompt,
            use_case=body.use_case,
            forced_tier=body.forced_tier,
            background_tasks=background_tasks,
        )
        if outcome["_status"] == 500:
            return JSONResponse(
                status_code=500, content=_error("provider_error", outcome["error"])
            )
        return {k: v for k, v in outcome.items() if k != "_status"}

    @app.get("/v1/models")
    def get_models():
        registry = load_registry()
        return {
            "models": [
                {
                    "provider": m.provider,
                    "id": m.id,
                    "tier": m.tier,
                    "price_in_per_m": m.price_in_per_m,
                    "price_out_per_m": m.price_out_per_m,
                }
                for m in registry.models
            ]
        }

    @app.get("/v1/stats")
    def get_stats(since: Optional[str] = None):
        if since is not None:
            try:
                datetime.fromisoformat(since)
            except ValueError:
                return JSONResponse(
                    status_code=422,
                    content=_error("invalid_since", "since must be an ISO timestamp"),
                )

        query = "SELECT tier_chosen, cost_all_tiers, judge_cost FROM runs"
        params: tuple = ()
        if since is not None:
            query += " WHERE created_at >= ?"
            params = (since,)
        rows = conn.execute(query, params).fetchall()

        by_tier = {t: 0 for t in KNOWN_TIERS}
        actual_cost_excl_judge = 0.0
        judge_cost_total = 0.0
        opus_cost = 0.0
        for row in rows:
            tier = row["tier_chosen"]
            by_tier[tier] = by_tier.get(tier, 0) + 1
            costs = json.loads(row["cost_all_tiers"]) if row["cost_all_tiers"] else {}
            if costs.get(tier) is not None:
                actual_cost_excl_judge += costs[tier]
            if costs.get("opus") is not None:
                opus_cost += costs["opus"]
            judge_cost_total += row["judge_cost"] or 0.0

        actual_cost_incl_judge = actual_cost_excl_judge + judge_cost_total

        def _saved_pct(actual_cost: float) -> float:
            return (1 - actual_cost / opus_cost) * 100 if opus_cost > 0 else 0.0

        # S4: a local-tier answer that gets judged by sonnet still cost one
        # sonnet call -- `saved_pct_incl_judge` folds that judge_cost into
        # the actual cost so it never overstates the saving (ADR 0001 /
        # Product_Scope §4). `saved_pct_excl_judge` is kept alongside it,
        # per the same section's "reported both ways, neither hidden" rule.
        return {
            "n_requests": len(rows),
            "by_tier": by_tier,
            "saved_pct_excl_judge": _saved_pct(actual_cost_excl_judge),
            "saved_pct_incl_judge": _saved_pct(actual_cost_incl_judge),
            "price_basis": "api_list_prices_no_money_changed_hands",
        }

    @app.put("/v1/routing-config")
    def put_routing_config(update: RoutingConfigUpdate):
        partial = update.model_dump(exclude_none=True)
        try:
            config = routing_config_module.update_config(routing_config_path, partial)
        except routing_config_module.InvalidConfigError as exc:
            return JSONResponse(
                status_code=422, content=_error("invalid_config", str(exc))
            )
        return config

    @app.get("/runs")
    def get_runs(
        page: int = 1,
        page_size: int = 20,
        tier: Optional[str] = None,
        use_case: Optional[str] = None,
        status: Optional[str] = None,
    ):
        if page < 1 or page_size < 1:
            return JSONResponse(
                status_code=422,
                content=_error("invalid_pagination", "page and page_size must be >= 1"),
            )

        where_clauses = []
        params: list = []
        if tier is not None:
            where_clauses.append("tier_chosen = ?")
            params.append(tier)
        if use_case is not None:
            where_clauses.append("use_case = ?")
            params.append(use_case)
        if status is not None:
            where_clauses.append("status = ?")
            params.append(status)
        where_sql = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        total_items = conn.execute(
            f"SELECT COUNT(*) FROM runs{where_sql}", params
        ).fetchone()[0]
        total_pages = math.ceil(total_items / page_size) if page_size else 0

        offset = (page - 1) * page_size
        rows = conn.execute(
            f"SELECT * FROM runs{where_sql} ORDER BY created_at DESC, run_id DESC "
            "LIMIT ? OFFSET ?",
            [*params, page_size, offset],
        ).fetchall()

        return {
            "data": [_run_row_to_dict(r) for r in rows],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_items": total_items,
                "total_pages": total_pages,
            },
        }

    @app.get("/runs/{run_id}/spans")
    def get_run_spans(run_id: str):
        run_row = conn.execute(
            "SELECT * FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if run_row is None:
            return JSONResponse(
                status_code=404,
                content=_error("run_not_found", f"no run with id {run_id!r}"),
            )

        span_rows = conn.execute(
            "SELECT * FROM spans WHERE run_id = ? ORDER BY start_ns ASC", (run_id,)
        ).fetchall()

        return {
            "run": _run_row_to_dict(run_row),
            "spans": [_span_row_to_dict(s) for s in span_rows],
        }

    @app.post("/replay")
    def post_replay(body: ReplayRequest, background_tasks: BackgroundTasks):
        source_row = conn.execute(
            "SELECT * FROM runs WHERE run_id = ?", (body.source_run_id,)
        ).fetchone()
        if source_row is None:
            return JSONResponse(
                status_code=404,
                content=_error(
                    "run_not_found", f"no run with id {body.source_run_id!r}"
                ),
            )

        # ADR 0002: re-run the WHOLE pipeline (classify -> select_tier ->
        # answer -> judge/escalate) against the source run's stored input,
        # with select_tier's output overridden to forced_tier. This is a
        # brand-new run (its own run_id + spans) -- never a mutation of the
        # source row -- because replay is non-deterministic: two replays of
        # the same source_run_id/forced_tier can produce different answers
        # and judge scores. The judge step runs synchronously here (unlike
        # /v1/completions) so diff_summary below can reflect the replay's
        # final outcome.
        outcome = _run_pipeline(
            prompt=source_row["input_text"],
            use_case=source_row["use_case"],
            forced_tier=body.forced_tier,
            background_tasks=background_tasks,
            synchronous_judge=True,
        )
        if outcome["_status"] == 500:
            return JSONResponse(
                status_code=500, content=_error("provider_error", outcome["error"])
            )

        new_run_id = outcome["run_id"]
        new_row = conn.execute(
            "SELECT * FROM runs WHERE run_id = ?", (new_run_id,)
        ).fetchone()
        diff_summary = _compute_diff(source_row, new_row)

        replay_id = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO replays (replay_id, source_run_id, forced_tier, "
            "new_run_id, created_at, diff_summary) VALUES (?,?,?,?,?,?)",
            (
                replay_id,
                body.source_run_id,
                body.forced_tier,
                new_run_id,
                datetime.now(timezone.utc).isoformat(),
                json.dumps(diff_summary),
            ),
        )
        conn.commit()

        return {
            "replay_id": replay_id,
            "new_run_id": new_run_id,
            "diff_summary": diff_summary,
        }

    return app


app = create_app()
