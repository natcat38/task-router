"""OTel wiring: a custom SQLite SpanExporter plus per-app TracerProvider
setup.

Tech_Scope.md §2 (spans schema), §3 (worked span sequence: router.classify,
router.select_tier, `chat <model>` with gen_ai.* attributes), and
otel-replay-options.md §2(c) (the ~30-line custom-exporter design this
mirrors) / §4 (the runs/spans schema).

Design choice: `setup_tracing()` builds its **own** `TracerProvider` per
call and returns it directly, instead of calling the OTel API's global
`trace.set_tracer_provider()`. The global provider can only be set once per
process (a second call is a silent no-op with a warning) -- fine for a
running service, but wrong for a test suite that builds a fresh `create_app()`
per test against a fresh temp SQLite file: a global provider would pin every
test's spans to whichever DB happened to call `setup_tracing()` first.
Span parent/child nesting does not depend on a shared global provider -- it
is tracked via `contextvars`-based context propagation, which
`start_as_current_span` participates in regardless of which provider's
tracer created a given span -- so each app instance gets full test
isolation for free.

Uses `SimpleSpanProcessor` (not `BatchSpanProcessor`) so a span is written
to SQLite the instant its `with` block exits, not after a batch interval --
required for tests that read the `spans` table immediately after a request
finishes.

NOTE on Traceloop/opentelemetry-instrumentation-ollama: that package
instruments the `ollama` *Python client* library. providers.py never
imports that client -- it calls Ollama's native `/api/chat` via stdlib
`urllib.request` (see local_request.py / providers._default_transport), so
Traceloop's Ollama instrumentation would never fire for this call path.
The `chat <model>` span is hand-rolled in api.py instead of relying on it
(Tech_Scope.md §5 S3 row).

Optional dual-export to an OTLP collector (e.g. Jaeger) behind
`OTEL_EXPORTER_OTLP_ENDPOINT` -- unset by default so CI/tests never need a
collector running. The OTLP exporter package is only imported when that
env var is set, so it is not a hard dependency of this project yet.
"""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Sequence, Tuple

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, Tracer, TracerProvider
from opentelemetry.sdk.trace.export import (
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)


class SQLiteSpanExporter(SpanExporter):
    """Writes finished spans directly into the `spans` table of the audit
    DB. This *is* the storage layer -- no separate collector needed
    (otel-replay-options.md §2(c))."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        try:
            for s in spans:
                ctx = s.get_span_context()
                self._conn.execute(
                    "INSERT INTO spans (span_id, run_id, parent_span_id, name, "
                    "start_ns, end_ns, attributes, status) VALUES (?,?,?,?,?,?,?,?)",
                    (
                        format(ctx.span_id, "016x"),
                        format(ctx.trace_id, "032x"),
                        format(s.parent.span_id, "016x") if s.parent else None,
                        s.name,
                        s.start_time,
                        s.end_time,
                        json.dumps(dict(s.attributes or {})),
                        s.status.status_code.name,
                    ),
                )
            self._conn.commit()
            return SpanExportResult.SUCCESS
        except Exception:  # noqa: BLE001 -- an exporter must never crash the app
            return SpanExportResult.FAILURE

    def shutdown(self) -> None:
        pass  # connection lifecycle belongs to db.py/api.py, not this exporter

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


def setup_tracing(conn: sqlite3.Connection) -> Tuple[Tracer, TracerProvider]:
    """Build a fresh TracerProvider wired to the SQLite exporter (+ optional
    OTLP dual-export), and return `(tracer, provider)`.

    `tracer` is used for the hand-rolled router/chat spans; `provider` is
    passed to `FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)`
    so the request-level root span lands in the same trace tree without
    touching the OTel global singleton (see module docstring).
    """
    provider = TracerProvider(resource=Resource.create({"service.name": "task-router"}))
    provider.add_span_processor(SimpleSpanProcessor(SQLiteSpanExporter(conn)))

    otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint))
        )

    return provider.get_tracer("router"), provider
