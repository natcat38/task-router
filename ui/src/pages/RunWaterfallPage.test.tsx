import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { RunWaterfallPage } from "./RunWaterfallPage";
import type { Run, RunSpansResponse, Span } from "../api/types";

function makeRun(overrides: Partial<Run> = {}): Run {
  return {
    run_id: "a3f9e1d2-0000-0000-0000-000000000000",
    created_at: "2026-01-05T12:04:00Z",
    input_text: "summarize this",
    input_features: null,
    use_case: "summarize",
    tier_chosen: "local",
    model_used: "qwen3:1.7b",
    output_text: "done",
    judge_score: 2,
    judge_label: "weak",
    escalated: false,
    escalation_chain: null,
    status: "ok",
    total_duration_ms: 120,
    cost_all_tiers: null,
    forced_tier: null,
    judge_cost: 0,
    ...overrides,
  };
}

function makeSpan(overrides: Partial<Span> = {}): Span {
  return {
    span_id: "span-1",
    run_id: "a3f9e1d2-0000-0000-0000-000000000000",
    parent_span_id: null,
    name: "router.classify",
    start_ns: 0,
    end_ns: 1_000_000,
    attributes: {},
    status: "OK",
    ...overrides,
  };
}

function renderAt(runId: string) {
  return render(
    <MemoryRouter initialEntries={[`/runs/${runId}`]}>
      <Routes>
        <Route path="/runs/:runId" element={<RunWaterfallPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("RunWaterfallPage", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the waterfall with correct nesting and durations, and opens the attribute drawer with gen_ai attrs", async () => {
    const response: RunSpansResponse = {
      run: makeRun(),
      spans: [
        makeSpan({
          span_id: "root",
          parent_span_id: null,
          name: "POST /v1/completions",
          start_ns: 0,
          end_ns: 5_000_000,
        }),
        makeSpan({
          span_id: "classify",
          parent_span_id: "root",
          name: "router.classify",
          start_ns: 0,
          end_ns: 1_000_000,
        }),
        makeSpan({
          span_id: "select",
          parent_span_id: "root",
          name: "router.select_tier",
          start_ns: 1_000_000,
          end_ns: 1_500_000,
        }),
        makeSpan({
          span_id: "chat",
          parent_span_id: "root",
          name: "chat qwen3:1.7b",
          start_ns: 1_500_000,
          end_ns: 4_500_000, // 3ms duration
          attributes: {
            "gen_ai.provider.name": "ollama",
            "gen_ai.request.model": "qwen3:1.7b",
            "gen_ai.usage.input_tokens": 42,
          },
        }),
      ],
    };

    fetchMock.mockResolvedValue({ ok: true, json: async () => response });

    renderAt("a3f9e1d2-0000-0000-0000-000000000000");

    // All four spans render as rows.
    expect(await screen.findByText("router.classify")).toBeInTheDocument();
    expect(screen.getByText("router.select_tier")).toBeInTheDocument();
    expect(screen.getByText("chat qwen3:1.7b")).toBeInTheDocument();
    expect(screen.getByText("POST /v1/completions")).toBeInTheDocument();

    // Duration for the chat span: (4_500_000 - 1_500_000) ns = 3ms.
    expect(screen.getByText("3.0ms")).toBeInTheDocument();

    // Clicking the chat span opens the attribute drawer with gen_ai keys surfaced.
    fireEvent.click(screen.getByText("chat qwen3:1.7b"));

    const drawer = await screen.findByRole("region", { name: /Attributes for chat qwen3:1.7b/ });
    expect(drawer).toBeInTheDocument();
    expect(screen.getByText("gen_ai.provider.name")).toBeInTheDocument();
    expect(screen.getByText('"ollama"')).toBeInTheDocument();
    expect(screen.getByText("gen_ai.request.model")).toBeInTheDocument();
  });

  it("shows the not-found state on a 404 from GET /runs/{id}/spans", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({
        error: { code: "not_found", message: "no such run", details: null },
      }),
    });

    renderAt("does-not-exist");

    expect(
      await screen.findByText(/No run with this ID. It may have aged out or the ID is wrong\./),
    ).toBeInTheDocument();
  });

  it("shows the loading state before the response resolves", () => {
    fetchMock.mockReturnValue(new Promise(() => {}));

    renderAt("a3f9e1d2-0000-0000-0000-000000000000");

    expect(screen.getByText("Reading trace…")).toBeInTheDocument();
  });
});
