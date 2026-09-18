"""S4: the background judge + one-step-at-a-time escalation (Tech_Scope.md
§3 steps 6-7, §5 S4 row; Product_Scope.md §3.2; ADR 0001).

The judge is always the tier one level above the tier that answered --
local answers are judged by sonnet, sonnet answers are judged by opus, opus
answers are never judged (there is no tier above opus, and grading a model
with itself is exactly the self-grading bias ADR 0001 avoids). Judging runs
on a sampled fraction (`judge_sample_rate` in routing.yaml). A score below
the use case's `judge_threshold` escalates exactly one tier -- never
straight to the top -- and the winning answer is swapped into the `runs`
row. If the escalated answer is *also* judged below threshold and another
tier remains above it, escalation repeats one more step: never skipping a
tier, but not capped at a single hop either -- this is why Tech_Scope §2
types `escalation_chain` as an *array* of `{tier, model, reason}` entries
rather than a single object, matching Product_Scope §3.2's "escalated one
tier at a time."

`judge_and_escalate()` is the entire background job. api.py schedules it as
a FastAPI `BackgroundTask` so it runs strictly after the response has
already gone back to the caller (Product_Scope §3.2: "the caller never
waits on anything below this line"). It never raises -- every provider
error or unparseable judge response is swallowed, logged onto the span, and
treated as "no score, no escalation" so a bad judge call can never take
down a request that already succeeded.
"""

from __future__ import annotations

import json
import random
import re
import sqlite3
from typing import Optional

from opentelemetry.trace import NonRecordingSpan, SpanContext, Status, StatusCode
from opentelemetry.trace import set_span_in_context

from task_router import routing_config as routing_config_module
from task_router.registry import Registry

# ADR 0001: local -> sonnet -> opus -> (none; opus is never judged).
_TIER_ABOVE = {"local": "sonnet", "sonnet": "opus", "opus": None}

DEFAULT_JUDGE_THRESHOLD = 4

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def judge_tier_above(tier: str) -> Optional[str]:
    """The tier that judges `tier`'s answers, or None if `tier` is the top
    of the chain (opus, or any unrecognised tier) -- ADR 0001."""
    return _TIER_ABOVE.get(tier)


def should_judge(sample_rate: float) -> bool:
    """Sampling gate against routing.yaml's judge_sample_rate. 0.0 never
    judges, 1.0 always judges (random.random() is in [0, 1), so it is
    always < 1.0 and never < 0.0 -- both boundaries are deterministic)."""
    return random.random() < sample_rate


def build_judge_prompt(prompt: str, routed_answer: str, use_case: str) -> str:
    """The instruction sent to the judge model. Asks for STRICT JSON only
    so `parse_judge_response` has something reliable to parse."""
    return (
        "You are a strict grader for an LLM router's quality safety net. "
        f"Score the ANSWER below against the PROMPT for the {use_case!r} "
        "use case, on an integer 1-5 scale (5 = excellent, fully correct "
        "and complete; 1 = unusable or wrong). Reply with STRICT JSON only "
        "-- no markdown, no commentary, no code fences -- in exactly this "
        'shape: {"score": <integer 1-5>, "reason": "<one short sentence>"}.'
        f"\n\nPROMPT:\n{prompt}\n\nANSWER:\n{routed_answer}"
    )


def parse_judge_response(text: str) -> Optional[dict]:
    """Parse the judge's STRICT JSON reply. Never raises: garbage text, a
    missing score, an out-of-range score, or a non-numeric score all yield
    None, which callers treat as no-score / no-escalation."""
    if not text:
        return None
    match = _JSON_OBJECT_RE.search(text)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    score = payload.get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        return None
    score = int(score)
    if not (1 <= score <= 5):
        return None
    reason = payload.get("reason")
    return {"score": score, "reason": reason if isinstance(reason, str) else ""}


def run_judge(send_fn, judge_model_id: str, prompt: str, routed_answer: str, use_case: str) -> dict:
    """Call the judge model via `send_fn` (providers.send-shaped: never
    raises). Always returns a dict; `score`/`reason` are None on any
    failure. `cost`/`input_tokens`/`output_tokens` are filled in whenever
    the provider call itself succeeded -- even if the reply couldn't be
    parsed, that call still cost real tokens and must count against the
    savings figure (ADR 0001: "judge tokens are counted in the savings
    figure")."""
    result = send_fn(build_judge_prompt(prompt, routed_answer, use_case), judge_model_id)
    outcome = {
        "score": None,
        "reason": None,
        "cost": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
        "provider_error": result.get("error"),
    }
    if result.get("error"):
        return outcome
    outcome["cost"] = result.get("cost", 0.0) or 0.0
    outcome["input_tokens"] = result.get("input_tokens", 0)
    outcome["output_tokens"] = result.get("output_tokens", 0)
    parsed = parse_judge_response(result.get("text", ""))
    if parsed is not None:
        outcome["score"] = parsed["score"]
        outcome["reason"] = parsed["reason"]
    return outcome


def _threshold_for(config: dict, use_case: str) -> int:
    use_cases = config.get("use_cases") or {}
    settings = use_cases.get(use_case) or {}
    return settings.get("judge_threshold", DEFAULT_JUDGE_THRESHOLD)


def judge_and_escalate(
    *,
    conn: sqlite3.Connection,
    tracer,
    parent_span_context: SpanContext,
    send_fn,
    registry: Registry,
    routing_config_path,
    run_id: str,
    prompt: str,
    use_case: str,
    tier_chosen: str,
    model_id: str,
    output_text: str,
) -> None:
    """The full S4 background job for one run: sample -> judge -> escalate
    (repeating one tier at a time while still under threshold and a tier
    remains) -> persist. Never raises.

    Reloads routing.yaml at call time (not at request time) so a live
    `PUT /v1/routing-config` edit (sample rate, thresholds) takes effect on
    the very next background job, per the "editable without restarting"
    design (Tech_Scope §4).

    `parent_span_context` is the request's root span context, captured by
    api.py *while it was still the ambient "current" span*. This job runs
    as a FastAPI `BackgroundTask`, strictly after the request handler (and
    its `with tracer.start_as_current_span(...)` blocks) have already
    exited, so there is no ambient span left to attach to via contextvars
    alone -- passing the parent explicitly is what keeps `router.judge` /
    `router.escalate` in the same trace, as direct children of the request
    root, instead of becoming spans of their own (Tech_Scope §2 spans
    table lists them as part of the same run's waterfall).
    """
    parent_ctx = set_span_in_context(NonRecordingSpan(parent_span_context))
    try:
        config = routing_config_module.load_config(routing_config_path)
    except FileNotFoundError:
        return

    if not should_judge(config.get("judge_sample_rate", 0.0)):
        return

    current_tier = tier_chosen
    current_model_id = model_id
    current_output = output_text
    escalation_chain: list[dict] = []
    total_judge_cost = 0.0
    final_score: Optional[int] = None
    final_label: Optional[str] = None
    attempted = False

    while True:
        judge_tier = judge_tier_above(current_tier)
        if judge_tier is None:
            break  # opus (or an unrecognised tier) -- no tier above it, unjudged by construction

        judge_model = registry.by_tier(judge_tier)
        attempted = True

        with tracer.start_as_current_span("router.judge", context=parent_ctx) as judge_span:
            judge_span.set_attribute("router.judge_tier", judge_tier)
            judge_span.set_attribute("gen_ai.request.model", judge_model.id)
            outcome = run_judge(send_fn, judge_model.id, prompt, current_output, use_case)
            if outcome["provider_error"]:
                judge_span.set_status(Status(StatusCode.ERROR, outcome["provider_error"]))
            elif outcome["score"] is None:
                judge_span.set_status(Status(StatusCode.ERROR, "unparseable judge response"))

        total_judge_cost += outcome["cost"]

        if outcome["score"] is None:
            # Provider error or garbage response: logged on the span above,
            # no score to act on, no escalation, no crash.
            break

        final_score = outcome["score"]
        threshold = _threshold_for(config, use_case)

        if final_score >= threshold:
            final_label = "pass"
            break

        final_label = "escalated"
        reason = f"judge_score={final_score}<{threshold}"

        with tracer.start_as_current_span("router.escalate", context=parent_ctx) as esc_span:
            esc_span.set_attribute("router.escalate_reason", reason)
            esc_span.set_attribute("router.escalate_to_tier", judge_tier)
            reanswer = send_fn(prompt, judge_model.id)

        if reanswer.get("error"):
            escalation_chain.append(
                {
                    "tier": judge_tier,
                    "model": judge_model.id,
                    "reason": f"{reason} (re-answer failed: {reanswer['error']})",
                }
            )
            break

        escalation_chain.append({"tier": judge_tier, "model": judge_model.id, "reason": reason})
        current_tier = judge_tier
        current_model_id = judge_model.id
        current_output = reanswer["text"]
        # Loop again: the newly escalated answer gets judged by ITS
        # tier-above in turn, so a still-bad answer can escalate once more
        # (Tech_Scope §3 step 7) -- but never past opus, and never two
        # tiers in a single hop.

    if not attempted:
        return  # opus tier: nothing was ever judged, nothing to persist

    escalated = bool(escalation_chain)
    conn.execute(
        "UPDATE runs SET judge_score=?, judge_label=?, escalated=?, "
        "escalation_chain=?, tier_chosen=?, model_used=?, output_text=?, "
        "judge_cost=? WHERE run_id=?",
        (
            final_score,
            final_label,
            1 if escalated else 0,
            json.dumps(escalation_chain) if escalation_chain else None,
            current_tier,
            current_model_id,
            current_output,
            total_judge_cost,
            run_id,
        ),
    )
    conn.commit()
