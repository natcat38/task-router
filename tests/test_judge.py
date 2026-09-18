"""S4: background judge + one-step-at-a-time escalation (Tech_Scope.md §5
S4 row, Product_Scope.md §3.2, ADR 0001). Fake provider only, temp SQLite
only -- no live judge call, no `claude -p`, no real model, per the S4 test
strategy.

The fake `send_fn` used below distinguishes a judge call from an answer /
re-answer call by looking for the "STRICT JSON" marker that
`judge.build_judge_prompt` always includes -- that marker is judge.py's own
contract with itself, so scripting against it is not testing an
implementation detail, it's testing the one thing that makes judge calls
distinguishable from answer calls at all.
"""

from __future__ import annotations

import json
import shutil

import pytest
import yaml
from opentelemetry.trace import SpanContext, TraceFlags

from task_router import db as db_module
from task_router import judge as judge_module
from task_router import tracing as tracing_module
from task_router.registry import load_registry

RUN_ID = format(0xABCDEF, "032x")


def _root_span_context() -> SpanContext:
    """A synthetic root span context standing in for the request span api.py
    would normally capture and pass down (see api.py's `root_span_context`).
    Its only job here is to give judge.py something to parent its spans
    under without crashing -- these tests assert on the `runs` row, not on
    span nesting (that's covered by test_api_completions.py)."""
    return SpanContext(
        trace_id=int(RUN_ID, 16),
        span_id=0x1,
        is_remote=False,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
    )


def _result(text="", *, cost=0.0, input_tokens=10, output_tokens=5, error=None):
    return {
        "text": text,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "latency": 0.0,
        "cost": cost,
        "error": error,
    }


@pytest.fixture
def conn(tmp_path):
    return db_module.get_connection(tmp_path / "audit.sqlite")


@pytest.fixture
def tracer(conn):
    tracer, _provider = tracing_module.setup_tracing(conn)
    return tracer


@pytest.fixture
def routing_yaml(tmp_path):
    dest = tmp_path / "routing.yaml"
    shutil.copy("routing.yaml", dest)
    return dest


def _set_sample_rate(routing_yaml_path, rate: float) -> None:
    config = yaml.safe_load(routing_yaml_path.read_text(encoding="utf-8"))
    config["judge_sample_rate"] = rate
    routing_yaml_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")


def _insert_run(conn, run_id, tier_chosen, model_used, output_text):
    conn.execute(
        "INSERT INTO runs (run_id, created_at, input_text, tier_chosen, "
        "model_used, output_text, status) VALUES (?,?,?,?,?,?,?)",
        (run_id, "2026-01-01T00:00:00+00:00", "Summarise this.", tier_chosen, model_used, output_text, "ok"),
    )
    conn.commit()


def _fetch_run(conn, run_id):
    return conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()


def _judge(conn, tracer, routing_yaml, send_fn, *, tier_chosen, model_id, output_text="original answer"):
    registry = load_registry()
    judge_module.judge_and_escalate(
        conn=conn,
        tracer=tracer,
        parent_span_context=_root_span_context(),
        send_fn=send_fn,
        registry=registry,
        routing_config_path=routing_yaml,
        run_id=RUN_ID,
        prompt="Summarise this.",
        use_case="summarise",
        tier_chosen=tier_chosen,
        model_id=model_id,
        output_text=output_text,
    )


# --- judge_tier_above (ADR 0001: tier above, opus unjudged) ---------------


def test_judge_tier_above_local_is_sonnet():
    assert judge_module.judge_tier_above("local") == "sonnet"


def test_judge_tier_above_sonnet_is_opus():
    assert judge_module.judge_tier_above("sonnet") == "opus"


def test_judge_tier_above_opus_is_none():
    assert judge_module.judge_tier_above("opus") is None


# --- should_judge (sampling gate) -----------------------------------------


def test_should_judge_rate_zero_never_judges():
    assert all(judge_module.should_judge(0.0) is False for _ in range(50))


def test_should_judge_rate_one_always_judges():
    assert all(judge_module.should_judge(1.0) is True for _ in range(50))


# --- parse_judge_response (never raises) ----------------------------------


def test_parse_judge_response_valid_json():
    parsed = judge_module.parse_judge_response('{"score": 3, "reason": "ok"}')
    assert parsed == {"score": 3, "reason": "ok"}


def test_parse_judge_response_extracts_json_from_surrounding_text():
    parsed = judge_module.parse_judge_response(
        'Sure, here is my score:\n{"score": 4, "reason": "solid"}\nThanks!'
    )
    assert parsed == {"score": 4, "reason": "solid"}


@pytest.mark.parametrize(
    "garbage",
    [
        "",
        "not json at all",
        "{not even valid json}",
        '{"score": "five", "reason": "bad type"}',
        '{"score": 9, "reason": "out of range"}',
        '{"reason": "missing score entirely"}',
        "null",
    ],
)
def test_parse_judge_response_garbage_yields_none(garbage):
    assert judge_module.parse_judge_response(garbage) is None


# --- run_judge (provider-call wrapper, never raises) ----------------------


def test_run_judge_provider_error_yields_no_score_and_zero_cost():
    def erroring_send(prompt, model):
        return _result(error="claude -p exited 1: boom")

    outcome = judge_module.run_judge(erroring_send, "sonnet", "p", "a", "summarise")
    assert outcome["score"] is None
    assert outcome["cost"] == 0.0
    assert outcome["provider_error"] == "claude -p exited 1: boom"


def test_run_judge_success_parses_score_and_carries_cost():
    def passing_send(prompt, model):
        return _result('{"score": 5, "reason": "great"}', cost=0.01)

    outcome = judge_module.run_judge(passing_send, "sonnet", "p", "a", "summarise")
    assert outcome["score"] == 5
    assert outcome["reason"] == "great"
    assert outcome["cost"] == 0.01
    assert outcome["provider_error"] is None


def test_run_judge_unparseable_reply_still_carries_cost():
    """A successful provider call that returns garbage still cost real
    tokens -- ADR 0001: judge tokens count against savings regardless of
    the score outcome."""

    def garbage_send(prompt, model):
        return _result("not json", cost=0.01, input_tokens=20, output_tokens=8)

    outcome = judge_module.run_judge(garbage_send, "sonnet", "p", "a", "summarise")
    assert outcome["score"] is None
    assert outcome["cost"] == 0.01


# --- judge_and_escalate: the full background job --------------------------


def test_low_score_escalates_exactly_one_tier_local_to_sonnet(conn, tracer, routing_yaml):
    def fake_send(prompt, model):
        if "STRICT JSON" in prompt:
            if model == "sonnet":
                return _result('{"score": 2, "reason": "wrong facts"}', cost=0.002)
            if model == "opus":
                return _result('{"score": 5, "reason": "good now"}', cost=0.01)
        return _result(f"{model} answer", cost=0.004)  # the re-answer call itself costs real money

    _insert_run(conn, RUN_ID, "local", "qwen3:1.7b", "local answer")
    _judge(
        conn, tracer, routing_yaml, fake_send,
        tier_chosen="local", model_id="qwen3:1.7b", output_text="local answer",
    )

    run = _fetch_run(conn, RUN_ID)
    chain = json.loads(run["escalation_chain"])
    assert run["escalated"] == 1
    assert len(chain) == 1  # exactly one tier step -- never straight to opus
    assert chain[0] == {"tier": "sonnet", "model": "sonnet", "reason": "judge_score=2<4"}
    assert run["tier_chosen"] == "sonnet"
    assert run["model_used"] == "sonnet"
    assert run["output_text"] == "sonnet answer"  # winning answer swapped in
    assert run["judge_score"] == 5  # final judge outcome, once the swapped answer passed
    assert run["judge_label"] == "pass"
    assert run["judge_cost"] > 0  # both judge calls (sonnet + opus) counted
    # Regression test for backend review Finding #1: the escalation
    # re-answer's real cost must be accumulated and persisted, not dropped.
    # One re-answer call happened (local -> sonnet), so escalation_cost is
    # exactly that call's cost.
    assert run["escalation_cost"] == pytest.approx(0.004)


def test_passing_score_does_not_escalate(conn, tracer, routing_yaml):
    def fake_send(prompt, model):
        assert "STRICT JSON" in prompt and model == "sonnet"
        return _result('{"score": 5, "reason": "great summary"}', cost=0.002)

    _insert_run(conn, RUN_ID, "local", "qwen3:1.7b", "local answer")
    _judge(
        conn, tracer, routing_yaml, fake_send,
        tier_chosen="local", model_id="qwen3:1.7b", output_text="local answer",
    )

    run = _fetch_run(conn, RUN_ID)
    assert run["escalated"] == 0
    assert run["escalation_chain"] is None
    assert run["tier_chosen"] == "local"
    assert run["output_text"] == "local answer"
    assert run["judge_score"] == 5
    assert run["judge_label"] == "pass"
    assert run["judge_cost"] > 0
    assert run["escalation_cost"] == 0  # no escalation happened -- nothing to accumulate


def test_failing_sonnet_answer_escalates_to_opus_one_step(conn, tracer, routing_yaml):
    def fake_send(prompt, model):
        if "STRICT JSON" in prompt:
            assert model == "opus"  # sonnet is judged by opus, never by itself
            return _result('{"score": 2, "reason": "shaky reasoning"}', cost=0.02)
        return _result(f"{model} answer")

    _insert_run(conn, RUN_ID, "sonnet", "sonnet", "sonnet original")
    _judge(
        conn, tracer, routing_yaml, fake_send,
        tier_chosen="sonnet", model_id="sonnet", output_text="sonnet original",
    )

    run = _fetch_run(conn, RUN_ID)
    chain = json.loads(run["escalation_chain"])
    assert run["escalated"] == 1
    assert len(chain) == 1
    assert chain[0]["tier"] == "opus"  # one step up from sonnet, never skipped
    assert run["tier_chosen"] == "opus"
    assert run["model_used"] == "opus"
    assert run["output_text"] == "opus answer"


def test_opus_tier_answer_is_never_judged(conn, tracer, routing_yaml):
    calls = []

    def spy_send(prompt, model):
        calls.append(model)
        return _result("should never be reached")

    _insert_run(conn, RUN_ID, "opus", "opus", "opus answer")
    _judge(
        conn, tracer, routing_yaml, spy_send,
        tier_chosen="opus", model_id="opus", output_text="opus answer",
    )

    assert calls == []  # no tier above opus -- judge never called (ADR 0001)
    run = _fetch_run(conn, RUN_ID)
    assert run["escalated"] == 0
    assert run["judge_score"] is None
    assert run["tier_chosen"] == "opus"


def test_sample_rate_zero_never_judges(conn, tracer, routing_yaml):
    _set_sample_rate(routing_yaml, 0.0)
    calls = []

    def spy_send(prompt, model):
        calls.append(model)
        return _result("should never be reached")

    _insert_run(conn, RUN_ID, "local", "qwen3:1.7b", "local answer")
    _judge(
        conn, tracer, routing_yaml, spy_send,
        tier_chosen="local", model_id="qwen3:1.7b", output_text="local answer",
    )

    assert calls == []
    run = _fetch_run(conn, RUN_ID)
    assert run["escalated"] == 0
    assert run["judge_score"] is None
    assert run["judge_cost"] == 0


def test_sample_rate_one_always_judges(conn, tracer, routing_yaml):
    _set_sample_rate(routing_yaml, 1.0)
    calls = []

    def fake_send(prompt, model):
        calls.append(model)
        return _result('{"score": 5, "reason": "fine"}', cost=0.002)

    _insert_run(conn, RUN_ID, "local", "qwen3:1.7b", "local answer")
    _judge(
        conn, tracer, routing_yaml, fake_send,
        tier_chosen="local", model_id="qwen3:1.7b", output_text="local answer",
    )

    assert calls == ["sonnet"]
    run = _fetch_run(conn, RUN_ID)
    assert run["judge_score"] == 5


def test_unparseable_judge_response_does_not_escalate_or_crash(conn, tracer, routing_yaml):
    def garbage_send(prompt, model):
        return _result("this is not json at all, sorry", cost=0.002)

    _insert_run(conn, RUN_ID, "local", "qwen3:1.7b", "local answer")

    _judge(  # must not raise
        conn, tracer, routing_yaml, garbage_send,
        tier_chosen="local", model_id="qwen3:1.7b", output_text="local answer",
    )

    run = _fetch_run(conn, RUN_ID)
    assert run["escalated"] == 0
    assert run["escalation_chain"] is None
    assert run["judge_score"] is None
    assert run["tier_chosen"] == "local"
    assert run["output_text"] == "local answer"
    assert run["judge_cost"] > 0  # the call itself still cost real tokens


def test_judge_provider_error_does_not_escalate_or_crash(conn, tracer, routing_yaml):
    def erroring_send(prompt, model):
        return _result(error="ollama transport error: connection refused")

    _insert_run(conn, RUN_ID, "local", "qwen3:1.7b", "local answer")

    _judge(  # must not raise
        conn, tracer, routing_yaml, erroring_send,
        tier_chosen="local", model_id="qwen3:1.7b", output_text="local answer",
    )

    run = _fetch_run(conn, RUN_ID)
    assert run["escalated"] == 0
    assert run["judge_score"] is None
    assert run["judge_cost"] == 0  # provider never actually answered -- no cost
