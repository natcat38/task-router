"""Tests for providers.py's send() interface (Tech_Scope.md §1/§2/§6).

No network, no claude -p: the ollama path is exercised through an injected
transport seam, and the claude_cli path is exercised through an injected
runner seam. Both seams let these tests assert real dispatch/parsing logic
without ever calling a live model (Tech_Scope.md §5, S1 test strategy).
"""

from __future__ import annotations

import json

import pytest

from task_router.providers import send


# ---------------------------------------------------------------------------
# send() never raises
# ---------------------------------------------------------------------------


def test_send_unknown_model_returns_error_not_raise():
    result = send("hi", "not-a-real-model")

    assert result["error"] is not None
    assert result["text"] == ""
    assert result["input_tokens"] == 0
    assert result["output_tokens"] == 0
    assert result["cost"] == 0.0


def test_send_ollama_transport_raising_becomes_error_field():
    def broken_transport(url, body, timeout):
        raise ConnectionRefusedError("no ollama running")

    result = send("hi", "qwen3:1.7b", transport=broken_transport)

    assert result["error"] is not None
    assert "no ollama running" in result["error"]
    assert result["text"] == ""
    assert result["cost"] == 0.0


def test_send_ollama_transport_bad_json_becomes_error_field():
    def garbage_transport(url, body, timeout):
        return "not json {{{"

    result = send("hi", "qwen3:1.7b", transport=garbage_transport)

    assert result["error"] is not None
    assert result["text"] == ""


def test_send_claude_cli_runner_timeout_becomes_error_field():
    import subprocess

    def timing_out_runner(args, input, capture_output, text, timeout, env):
        raise subprocess.TimeoutExpired(cmd=args, timeout=timeout)

    result = send("hi", "sonnet", runner=timing_out_runner)

    assert result["error"] is not None
    assert result["text"] == ""
    assert result["cost"] == 0.0


def test_send_claude_cli_runner_nonzero_exit_becomes_error_field():
    class FakeCompletedProcess:
        returncode = 1
        stdout = ""
        stderr = "boom"

    def failing_runner(args, input, capture_output, text, timeout, env):
        return FakeCompletedProcess()

    result = send("hi", "sonnet", runner=failing_runner)

    assert result["error"] is not None
    assert "boom" in result["error"]


def test_send_claude_cli_runner_garbage_json_becomes_error_field():
    class FakeCompletedProcess:
        returncode = 0
        stdout = "not json {{{"
        stderr = ""

    def garbage_runner(args, input, capture_output, text, timeout, env):
        return FakeCompletedProcess()

    result = send("hi", "sonnet", runner=garbage_runner)

    assert result["error"] is not None


# ---------------------------------------------------------------------------
# Ollama success path
# ---------------------------------------------------------------------------


def test_send_ollama_success_parses_text_and_tokens():
    captured = {}

    def fake_transport(url, body, timeout):
        captured["url"] = url
        captured["body"] = body
        return json.dumps(
            {
                "message": {"content": "hello back"},
                "prompt_eval_count": 12,
                "eval_count": 7,
            }
        )

    result = send("hi", "qwen3:1.7b", transport=fake_transport)

    assert result["error"] is None
    assert result["text"] == "hello back"
    assert result["input_tokens"] == 12
    assert result["output_tokens"] == 7
    assert result["cost"] == 0.0
    assert result["latency"] >= 0
    assert "11434" in captured["url"]


def test_send_ollama_posts_think_false_body():
    captured = {}

    def fake_transport(url, body, timeout):
        captured["body"] = body
        return json.dumps({"message": {"content": "x"}, "prompt_eval_count": 1, "eval_count": 1})

    send("hi", "qwen3:1.7b", transport=fake_transport)

    assert captured["body"]["think"] is False


def test_send_ollama_uses_ollama_host_env(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://example-host:9999")
    captured = {}

    def fake_transport(url, body, timeout):
        captured["url"] = url
        return json.dumps({"message": {"content": "x"}, "prompt_eval_count": 1, "eval_count": 1})

    send("hi", "qwen3:1.7b", transport=fake_transport)

    assert captured["url"].startswith("http://example-host:9999")


# ---------------------------------------------------------------------------
# claude_cli success path + env/--bare safety
# ---------------------------------------------------------------------------


def _claude_cli_payload(result_text="hello from claude", input_tokens=100, output_tokens=50):
    return json.dumps(
        {
            "result": result_text,
            "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
        }
    )


def test_send_claude_cli_success_parses_result_and_usage():
    class FakeCompletedProcess:
        returncode = 0
        stdout = _claude_cli_payload()
        stderr = ""

    def fake_runner(args, input, capture_output, text, timeout, env):
        return FakeCompletedProcess()

    result = send("hi", "sonnet", runner=fake_runner)

    assert result["error"] is None
    assert result["text"] == "hello from claude"
    assert result["input_tokens"] == 100
    assert result["output_tokens"] == 50
    assert result["cost"] == pytest.approx(2.0 * 0.0001 + 10.0 * 0.00005)


def test_send_claude_cli_strips_api_key_env_vars():
    captured = {}

    class FakeCompletedProcess:
        returncode = 0
        stdout = _claude_cli_payload()
        stderr = ""

    def fake_runner(args, input, capture_output, text, timeout, env):
        captured["env"] = env
        captured["args"] = args
        return FakeCompletedProcess()

    import os

    os.environ["ANTHROPIC_API_KEY"] = "sk-should-be-stripped"
    os.environ["ANTHROPIC_AUTH_TOKEN"] = "token-should-be-stripped"
    try:
        send("hi", "sonnet", runner=fake_runner)
    finally:
        os.environ.pop("ANTHROPIC_API_KEY", None)
        os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)

    assert "ANTHROPIC_API_KEY" not in captured["env"]
    assert "ANTHROPIC_AUTH_TOKEN" not in captured["env"]


def test_send_claude_cli_never_passes_bare_flag():
    captured = {}

    class FakeCompletedProcess:
        returncode = 0
        stdout = _claude_cli_payload()
        stderr = ""

    def fake_runner(args, input, capture_output, text, timeout, env):
        captured["args"] = args
        return FakeCompletedProcess()

    send("hi", "opus", runner=fake_runner)

    assert "--bare" not in captured["args"]
    assert "-p" in captured["args"]
    assert "--output-format" in captured["args"]
    assert "json" in captured["args"]
    assert "opus" in captured["args"]


def test_send_claude_cli_passes_prompt_via_input_not_stdin_pipe():
    captured = {}

    class FakeCompletedProcess:
        returncode = 0
        stdout = _claude_cli_payload()
        stderr = ""

    def fake_runner(args, input, capture_output, text, timeout, env):
        captured["input"] = input
        return FakeCompletedProcess()

    send("summarise this", "sonnet", runner=fake_runner)

    assert captured["input"] == "summarise this"


# ---------------------------------------------------------------------------
# Fake provider used by the rest of the test suite / baseline.py tests
# ---------------------------------------------------------------------------


def test_fake_provider_returns_canned_response():
    from task_router.fake_provider import FakeProvider

    fake = FakeProvider(text="canned", input_tokens=10, output_tokens=5)

    result = fake.send("any prompt", "sonnet")

    assert result["error"] is None
    assert result["text"] == "canned"
    assert result["input_tokens"] == 10
    assert result["output_tokens"] == 5
    assert result["cost"] == pytest.approx(2.0 * 0.00001 + 10.0 * 0.000005)


def test_fake_provider_can_simulate_an_error():
    from task_router.fake_provider import FakeProvider

    fake = FakeProvider(error="simulated failure")

    result = fake.send("any prompt", "sonnet")

    assert result["error"] == "simulated failure"
    assert result["text"] == ""
    assert result["input_tokens"] == 0
    assert result["output_tokens"] == 0
    assert result["cost"] == 0.0
