"""The pinned local-tier (Ollama) chat request body.

One pure function, no I/O. Its whole job is to keep `"think": False` in the
request body under one name so a future edit to the local-tier call site
can't silently drop it (Tech_Scope.md §6 gotcha: qwen3:1.7b runs with
thinking mode ON by default in Ollama, and leaving it on inflates the
latency/token numbers this project exists to report honestly).

See docs/research/ollama-local-tier.md §4 for the native /api/chat contract
this body is shaped for.
"""

from __future__ import annotations

DEFAULT_MODEL = "qwen3:1.7b"


def build_local_chat_request(prompt: str, model: str = DEFAULT_MODEL) -> dict:
    """Build the native Ollama /api/chat request body for the local tier.

    Always non-streaming and always think:false -- both are pinned here on
    purpose, not left to the caller, so that changing them requires editing
    this one function (and its test) rather than a call site.
    """
    return {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "think": False,
    }
