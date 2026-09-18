"""The single provider interface: send(prompt, model) -> result dict.

Tech_Scope.md §1/§2/§6. `send()` never raises -- any failure (timeout,
non-zero exit, bad JSON, connection refused) comes back as a non-null
`error` string with every other field zeroed/empty, so callers never need
a try/except around it.

Dispatch is on the model's `provider` field in registry.yaml:
- `ollama`: POST the pinned think:false body (local_request.py) to the
  native /api/chat endpoint via stdlib urllib.
- `claude_cli`: run `claude -p --output-format json --model <id>` via
  subprocess, input piped through `input=` (never a dangling stdin pipe --
  claude-p-backend.md §4 Windows gotcha), child env stripped of
  ANTHROPIC_API_KEY/ANTHROPIC_AUTH_TOKEN so it never falls off the Max
  subscription onto API-key billing, and never --bare (Tech_Scope.md §6).

The network/subprocess call is injectable (`transport`/`runner`) purely so
tests can exercise the real dispatch/parsing logic without a network call
or a live claude -p invocation -- not a general plugin system, just a seam.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request
from typing import Callable, Optional

from task_router.local_request import build_local_chat_request
from task_router.registry import load_registry

OLLAMA_TIMEOUT_S = 60
CLAUDE_CLI_TIMEOUT_S = 120

Result = dict

TransportFn = Callable[[str, dict, float], str]
RunnerFn = Callable[..., object]


def _empty_error_result(error: str) -> Result:
    return {
        "text": "",
        "input_tokens": 0,
        "output_tokens": 0,
        "latency": 0.0,
        "cost": 0.0,
        "error": error,
    }


def _default_transport(url: str, body: dict, timeout: float) -> str:
    """Real stdlib-urllib POST to Ollama's native /api/chat. No new HTTP dep."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def _default_runner(
    args: list[str],
    input: str,
    capture_output: bool,
    text: bool,
    timeout: float,
    env: dict,
):
    """Real subprocess.run wrapper for `claude -p`."""
    return subprocess.run(
        args, input=input, capture_output=capture_output, text=text, timeout=timeout, env=env
    )


def _subscription_env() -> dict:
    """Child env with API-key auth stripped so claude -p stays on the Max
    subscription's OAuth session instead of silently switching to metered
    API-key billing (Tech_Scope.md §6)."""
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("ANTHROPIC_AUTH_TOKEN", None)
    return env


def _send_ollama(prompt: str, model_id: str, transport: TransportFn) -> Result:
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    url = f"{host}/api/chat"
    body = build_local_chat_request(prompt, model=model_id)

    start = time.monotonic()
    try:
        raw = transport(url, body, OLLAMA_TIMEOUT_S)
    except Exception as exc:  # noqa: BLE001 -- send() must never raise
        return _empty_error_result(f"ollama transport error: {exc}")
    latency = time.monotonic() - start

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        return _empty_error_result(f"ollama returned invalid JSON: {exc}")

    try:
        text_out = payload["message"]["content"]
        input_tokens = payload["prompt_eval_count"]
        output_tokens = payload["eval_count"]
    except (KeyError, TypeError) as exc:
        return _empty_error_result(f"ollama response missing expected field: {exc}")

    return {
        "text": text_out,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "latency": latency,
        "cost": 0.0,
        "error": None,
    }


def _send_claude_cli(prompt: str, model_id: str, runner: RunnerFn, cost_fn) -> Result:
    args = ["claude", "-p", "--output-format", "json", "--model", model_id]
    env = _subscription_env()

    start = time.monotonic()
    try:
        completed = runner(
            args,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=CLAUDE_CLI_TIMEOUT_S,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        return _empty_error_result(f"claude -p timed out: {exc}")
    except Exception as exc:  # noqa: BLE001 -- send() must never raise
        return _empty_error_result(f"claude -p failed to start: {exc}")
    latency = time.monotonic() - start

    if completed.returncode != 0:
        return _empty_error_result(
            f"claude -p exited {completed.returncode}: {completed.stderr.strip()[:500]}"
        )

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return _empty_error_result(f"claude -p returned invalid JSON: {exc}")

    try:
        text_out = payload["result"]
        usage = payload["usage"]
        # int(...) both validates and normalizes: a well-formed response has
        # these as ints already, but coercing here (rather than using them
        # raw) means a numeric-looking-but-wrong-type field (e.g. a string)
        # is caught by the except clause below instead of raising out of
        # cost_fn()'s arithmetic below send()'s try/except -- see
        # test_send_claude_cli_non_numeric_usage_becomes_error_field.
        input_tokens = int(usage["input_tokens"])
        output_tokens = int(usage["output_tokens"])
    except (KeyError, TypeError, ValueError) as exc:
        return _empty_error_result(f"claude -p response missing expected field: {exc}")

    try:
        cost = cost_fn(model_id, input_tokens, output_tokens)
    except Exception as exc:  # noqa: BLE001 -- send() must never raise
        return _empty_error_result(f"claude -p cost computation failed: {exc}")

    return {
        "text": text_out,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "latency": latency,
        "cost": cost,
        "error": None,
    }


def send(
    prompt: str,
    model: str,
    *,
    transport: Optional[TransportFn] = None,
    runner: Optional[RunnerFn] = None,
) -> Result:
    """Send `prompt` to `model` (a registry.yaml model id). Never raises.

    `transport` overrides the Ollama HTTP call; `runner` overrides the
    claude -p subprocess call. Both are test seams -- production code
    should never need to pass them.
    """
    try:
        registry = load_registry()
        entry = registry.by_id(model)
    except Exception as exc:  # noqa: BLE001 -- send() must never raise
        return _empty_error_result(f"unknown model {model!r}: {exc}")

    if entry.provider == "ollama":
        return _send_ollama(prompt, entry.id, transport or _default_transport)
    if entry.provider == "claude_cli":
        return _send_claude_cli(
            prompt, entry.id, runner or _default_runner, registry.cost
        )
    return _empty_error_result(f"no dispatch for provider {entry.provider!r}")
