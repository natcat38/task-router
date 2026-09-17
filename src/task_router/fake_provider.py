"""A canned/erroring stand-in for providers.send(), used by every test and
by baseline.py's own unit tests (Tech_Scope.md §1: "a fake implementation
used by every test and by CI"). No network, no subprocess, ever.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from task_router.providers import Result
from task_router.registry import load_registry


@dataclass
class FakeProvider:
    """Returns a canned response, or a simulated error when `error` is set."""

    text: str = "fake response"
    input_tokens: int = 0
    output_tokens: int = 0
    error: Optional[str] = None

    def send(self, prompt: str, model: str) -> Result:
        if self.error is not None:
            return {
                "text": "",
                "input_tokens": 0,
                "output_tokens": 0,
                "latency": 0.0,
                "cost": 0.0,
                "error": self.error,
            }

        registry = load_registry()
        cost = registry.cost(model, self.input_tokens, self.output_tokens)
        return {
            "text": self.text,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "latency": 0.0,
            "cost": cost,
            "error": None,
        }
