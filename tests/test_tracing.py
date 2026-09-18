"""Tests for the OTLP endpoint normalization in tracing.py.

`OTLPSpanExporter(endpoint=...)` treats its argument as the full traces URL,
not a base -- so the README's documented base value (`http://localhost:4318`)
needs `/v1/traces` appended before it reaches the exporter, or Jaeger's OTLP
HTTP receiver never sees the request. `_normalize_otlp_endpoint` is a pure
string helper, so it is tested directly here without standing up a real
collector.
"""

from __future__ import annotations

from task_router.tracing import _normalize_otlp_endpoint


def test_appends_v1_traces_to_bare_base() -> None:
    assert (
        _normalize_otlp_endpoint("http://localhost:4318")
        == "http://localhost:4318/v1/traces"
    )


def test_strips_trailing_slash_before_appending() -> None:
    assert (
        _normalize_otlp_endpoint("http://localhost:4318/")
        == "http://localhost:4318/v1/traces"
    )


def test_leaves_fully_qualified_endpoint_unchanged() -> None:
    assert (
        _normalize_otlp_endpoint("http://collector:4318/v1/traces")
        == "http://collector:4318/v1/traces"
    )


def test_leaves_fully_qualified_endpoint_with_trailing_slash_unchanged() -> None:
    # Trailing slash is stripped first, so a URL that ends in /v1/traces/
    # collapses to the canonical form rather than gaining a duplicate segment.
    assert (
        _normalize_otlp_endpoint("http://collector:4318/v1/traces/")
        == "http://collector:4318/v1/traces"
    )
