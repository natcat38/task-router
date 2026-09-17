"""FastAPI app: the synchronous request lifecycle (Tech_Scope.md §4) --
`POST /v1/completions` (classify -> route -> answer -> audit row + spans),
`GET /v1/models`, `GET /v1/stats`, `PUT /v1/routing-config`.

This is S3 only (Tech_Scope §5): the background judge/escalation (S4) and
the replay read-API (S5, `GET /runs`, `GET /runs/{id}/spans`, `POST
/replay`) are NOT built here. `forced_tier` is accepted on the request body
and recorded on the `runs` row now, exactly per Tech_Scope §5's S3 row,
purely so S5 can reuse this same code path unchanged later -- there is no
replay endpoint yet.

`create_app()` is a factory, not a module-level singleton, so tests can
build an isolated instance against a temp SQLite file, a fake provider, and
a stub classifier (module seams -- Tech_Scope §5 S3 test strategy) without
ever touching Ollama or `claude -p`. `app = create_app()` at the bottom is
the default instance `uvicorn api:app` serves.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.trace import Status, StatusCode
from pydantic import BaseModel, field_validator

from task_router import classifier as classifier_module
from task_router import db as db_module
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


def _error(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message, "details": None}}


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

    @app.post("/v1/completions")
    def post_completions(body: CompletionRequest):
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

        with tracer.start_as_current_span("router.classify") as classify_span:
            features = extract_features(body.prompt)
            classify_span.set_attribute("router.features", json.dumps(features))
            run_id = format(classify_span.get_span_context().trace_id, "032x")

        with tracer.start_as_current_span("router.select_tier") as tier_span:
            if body.forced_tier is not None:
                tier = body.forced_tier
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
            result = send(body.prompt, model_entry.id)
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
            "tier_chosen, model_used, output_text, status, total_duration_ms, "
            "cost_all_tiers, forced_tier) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                run_id,
                datetime.now(timezone.utc).isoformat(),
                body.prompt,
                json.dumps(features),
                tier,
                model_entry.id,
                result["text"],
                status,
                None,
                json.dumps(cost_all_tiers),
                body.forced_tier,
            ),
        )
        conn.commit()

        if result["error"]:
            return JSONResponse(
                status_code=500, content=_error("provider_error", result["error"])
            )

        return {
            "run_id": run_id,
            "tier_chosen": tier,
            "model_used": model_entry.id,
            "output_text": result["text"],
            "cost_all_tiers": cost_all_tiers,
        }

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

        query = "SELECT tier_chosen, cost_all_tiers FROM runs"
        params: tuple = ()
        if since is not None:
            query += " WHERE created_at >= ?"
            params = (since,)
        rows = conn.execute(query, params).fetchall()

        by_tier = {t: 0 for t in KNOWN_TIERS}
        actual_cost = 0.0
        opus_cost = 0.0
        for row in rows:
            tier = row["tier_chosen"]
            by_tier[tier] = by_tier.get(tier, 0) + 1
            costs = json.loads(row["cost_all_tiers"]) if row["cost_all_tiers"] else {}
            if costs.get(tier) is not None:
                actual_cost += costs[tier]
            if costs.get("opus") is not None:
                opus_cost += costs["opus"]

        saved_pct = (1 - actual_cost / opus_cost) * 100 if opus_cost > 0 else 0.0

        # Judge cost doesn't exist until S4 (background judge/escalation) --
        # judge tokens are 0 for now, so incl == excl. The field is split
        # into two now, per Product_Scope §4, so S4 only has to fill
        # `saved_pct_incl_judge` in without a response-shape change.
        return {
            "n_requests": len(rows),
            "by_tier": by_tier,
            "saved_pct_excl_judge": saved_pct,
            "saved_pct_incl_judge": saved_pct,
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

    return app


app = create_app()
