import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ReplayPanel } from "./ReplayPanel";
import type { Run } from "../api/types";

function makeRun(overrides: Partial<Run> = {}): Run {
  return {
    run_id: "source-run-1",
    created_at: "2026-01-05T12:04:00Z",
    input_text: "summarize this",
    input_features: null,
    use_case: "summarize",
    tier_chosen: "local",
    model_used: "qwen3:1.7b",
    output_text: "short summary",
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

describe("ReplayPanel", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("posts to /replay, then renders the diff summary as a before/after and links to the new run", async () => {
    let resolvePost: ((value: unknown) => void) | undefined;
    const postPromise = new Promise((resolve) => {
      resolvePost = resolve;
    });

    fetchMock.mockImplementation((_url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        return postPromise;
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({
          run: makeRun({
            run_id: "new-run-2",
            tier_chosen: "opus",
            model_used: "opus",
            judge_score: 4,
            judge_label: "strong",
            output_text: "much better summary",
            forced_tier: "opus",
          }),
          spans: [],
        }),
      });
    });

    render(
      <MemoryRouter>
        <ReplayPanel sourceRunId="source-run-1" sourceRun={makeRun()} />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText("Forced tier"), { target: { value: "opus" } });
    fireEvent.click(screen.getByRole("button", { name: "Replay" }));

    expect(await screen.findByText(/Replaying against opus/)).toBeInTheDocument();

    resolvePost?.({
      ok: true,
      json: async () => ({
        replay_id: "replay-1",
        new_run_id: "new-run-2",
        diff_summary: {
          tier_changed: true,
          model_changed: true,
          judge_score_delta: 2,
          output_changed: true,
        },
      }),
    });

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

    const postCall = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(String(postCall?.[1]?.body)).toContain('"forced_tier":"opus"');
    expect(String(postCall?.[1]?.body)).toContain('"source_run_id":"source-run-1"');

    // Before/after tier and model values.
    expect(await screen.findByText("qwen3:1.7b")).toBeInTheDocument();
    expect(screen.getAllByText("opus").length).toBeGreaterThan(0);

    // Non-deterministic / separate-run note per ADR 0002.
    expect(screen.getByText(/does not correct or overwrite the original/)).toBeInTheDocument();

    const link = screen.getByRole("link", { name: /View new run/ });
    expect(link).toHaveAttribute("href", "/runs/new-run-2");
  });

  it("shows a failure message when the replay request errors", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({
        error: { code: "not_found", message: "no such run", details: null },
      }),
    });

    render(
      <MemoryRouter>
        <ReplayPanel sourceRunId="source-run-1" sourceRun={makeRun()} />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Replay" }));

    expect(await screen.findByText(/Replay failed: no such run/)).toBeInTheDocument();
  });
});
