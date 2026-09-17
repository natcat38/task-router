"""S0 smoke test: Windows subprocess/stdin safety for `claude -p`, plus one
Ollama `/api/chat` call proving `think: false` is honored.

Not a battery, not CI — a one-time manual check that the two provider
backends behave on this machine before S1 builds `providers.py` on top of
them. Run with:

    uv run python scripts/smoke_claude.py

References:
- docs/research/claude-p-backend.md §1 (JSON fields), §4 (Windows stdin bug
  fixed at v2.1.211; use subprocess.run(..., input=<str>) with no dangling
  stdin pipe).
- docs/research/ollama-local-tier.md §4 (native /api/chat fields).
- docs/Tech_Scope.md §6 (strip ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN from
  the child env so claude -p never silently falls back to API-key billing).
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

CLAUDE_PROMPT = "Reply with the single word: ok"
CLAUDE_CALLS = 5
CLAUDE_TIMEOUT_S = 60

OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "qwen3:1.7b"
OLLAMA_TIMEOUT_S = 60


def subscription_env() -> dict[str, str]:
    """A copy of the parent environment with API-key auth removed.

    If ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN happen to be set in the
    parent shell, an unmodified `claude` binary prefers API-key billing over
    the OAuth/subscription session -- silently moving calls onto metered
    billing. Strip both so every call in this script stays on the Max
    subscription (Tech_Scope.md §6).
    """
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("ANTHROPIC_AUTH_TOKEN", None)
    return env


def run_claude_smoke() -> bool:
    """Run `claude -p` five times back-to-back; return True iff all succeed.

    Windows-safe pattern per claude-p-backend.md §4: pass the prompt via
    `input=` as a single subprocess.run call (no persistent stdin pipe left
    open, no interactive handshake) and always set an explicit timeout so a
    hang is visible instead of blocking forever.
    """
    import subprocess

    env = subscription_env()
    all_ok = True

    for i in range(1, CLAUDE_CALLS + 1):
        try:
            result = subprocess.run(
                ["claude", "-p", "--output-format", "json", "--model", "sonnet"],
                input=CLAUDE_PROMPT,
                capture_output=True,
                text=True,
                timeout=CLAUDE_TIMEOUT_S,
                env=env,
            )
        except subprocess.TimeoutExpired:
            print(f"[claude call {i}/{CLAUDE_CALLS}] FAIL: timed out after {CLAUDE_TIMEOUT_S}s")
            all_ok = False
            continue

        if result.returncode != 0:
            print(f"[claude call {i}/{CLAUDE_CALLS}] FAIL: exit {result.returncode}: {result.stderr.strip()[:300]}")
            all_ok = False
            continue

        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            print(f"[claude call {i}/{CLAUDE_CALLS}] FAIL: could not parse JSON output: {exc}")
            all_ok = False
            continue

        text = payload.get("result")
        is_error = payload.get("is_error")
        if is_error or not text:
            print(f"[claude call {i}/{CLAUDE_CALLS}] FAIL: is_error={is_error} result={text!r}")
            all_ok = False
            continue

        print(f"[claude call {i}/{CLAUDE_CALLS}] OK: result={text!r} cost_usd(estimate)={payload.get('total_cost_usd')}")

    return all_ok


def run_ollama_think_false_smoke() -> bool:
    """One native /api/chat call with think:false; confirm no thinking output.

    Per ollama-local-tier.md §4, only the native /api/chat endpoint carries
    the extra fields we need; per Tech_Scope.md §6, qwen3:1.7b runs with
    thinking ON by default, so this call must set "think": false explicitly
    and this smoke test must prove that flag actually suppresses it (no
    <think> block, no separate "thinking" field in the message).
    """
    body = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": "Reply with the single word: ok"}],
        "stream": False,
        "think": False,
    }
    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT_S) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - smoke test, report and fail loudly
        print(f"[ollama think:false] FAIL: request error: {exc}")
        return False

    message = payload.get("message", {})
    content = message.get("content", "")
    thinking_field = message.get("thinking")

    if thinking_field:
        print(f"[ollama think:false] FAIL: unexpected 'thinking' field present: {thinking_field!r}")
        return False
    if "<think>" in content:
        print(f"[ollama think:false] FAIL: <think> block leaked into content: {content!r}")
        return False
    if not content.strip():
        print("[ollama think:false] FAIL: empty content")
        return False

    print(f"[ollama think:false] OK: content={content!r}")
    return True


def main() -> int:
    print("--- claude -p Windows stdin smoke test (5 back-to-back calls) ---")
    claude_ok = run_claude_smoke()

    print()
    print("--- Ollama think:false smoke test ---")
    ollama_ok = run_ollama_think_false_smoke()

    print()
    print(f"claude -p: {'PASS' if claude_ok else 'FAIL'}")
    print(f"ollama think:false: {'PASS' if ollama_ok else 'FAIL'}")

    return 0 if (claude_ok and ollama_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
