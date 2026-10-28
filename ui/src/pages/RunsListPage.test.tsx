import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, RouterProvider, createMemoryRouter } from "react-router-dom";
import { RunsListPage } from "./RunsListPage";
import type { Run, RunsListResponse } from "../api/types";

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
    judge_score: null,
    judge_label: null,
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

function makeResponse(overrides: Partial<RunsListResponse> = {}): RunsListResponse {
  return {
    data: [makeRun()],
    pagination: { page: 1, page_size: 20, total_items: 1, total_pages: 1 },
    ...overrides,
  };
}

describe("RunsListPage", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders rows from a mocked GET /runs response", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () =>
        makeResponse({
          data: [
            makeRun({ run_id: "a3f9e1d2-aaaa", use_case: "extract", tier_chosen: "sonnet", status: "ok" }),
            makeRun({ run_id: "b2c81099-bbbb", use_case: "summarize", tier_chosen: "opus", escalated: true }),
          ],
        }),
    });

    render(
      <MemoryRouter initialEntries={["/"]}>
        <RunsListPage />
      </MemoryRouter>,
    );

    expect((await screen.findAllByText("extract")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("summarize").length).toBeGreaterThan(0);
    expect(screen.getAllByText("sonnet").length).toBeGreaterThan(0);
    expect(screen.getAllByText("opus").length).toBeGreaterThan(0);
    expect(screen.getAllByText("escalated").length).toBeGreaterThan(0);
  });

  it("shows the empty-state copy when GET /runs returns no rows", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => makeResponse({ data: [], pagination: { page: 1, page_size: 20, total_items: 0, total_pages: 0 } }),
    });

    render(
      <MemoryRouter initialEntries={["/"]}>
        <RunsListPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText(/No runs yet/)).toBeInTheDocument();
  });

  it("advances the page query param when Next is clicked", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () =>
        makeResponse({ pagination: { page: 1, page_size: 20, total_items: 40, total_pages: 2 } }),
    });

    render(
      <MemoryRouter initialEntries={["/"]}>
        <RunsListPage />
      </MemoryRouter>,
    );

    await screen.findByText(/Page 1 of 2/);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    await waitFor(() => {
      const lastCall = fetchMock.mock.calls.at(-1);
      const url = String(lastCall?.[0]);
      expect(url).toContain("page=2");
    });
  });

  it("sets the tier query param when a filter is chosen", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => makeResponse(),
    });

    render(
      <MemoryRouter initialEntries={["/"]}>
        <RunsListPage />
      </MemoryRouter>,
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    fireEvent.change(screen.getByLabelText("Tier"), { target: { value: "sonnet" } });

    await waitFor(() => {
      const lastCall = fetchMock.mock.calls.at(-1);
      const url = String(lastCall?.[0]);
      expect(url).toContain("tier=sonnet");
    });
  });

  it("shows the unreachable-API copy on a network failure", async () => {
    fetchMock.mockRejectedValue(new TypeError("network down"));

    render(
      <MemoryRouter initialEntries={["/"]}>
        <RunsListPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText(/Couldn't reach the router API/)).toBeInTheDocument();
  });

  // TR-UX-3: the list says what each request was.
  it("shows the request text in each row, with the full text in the tooltip, and the whole row opens the run", async () => {
    const long = "Summarise this incident report for the on-call channel. ".repeat(10);
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => makeResponse({ data: [makeRun({ run_id: "run-1", input_text: long })] }),
    });
    const router = createMemoryRouter(
      [
        { path: "/", element: <RunsListPage /> },
        { path: "/runs/:runId", element: <p>run page</p> },
      ],
      { initialEntries: ["/"] },
    );
    render(<RouterProvider router={router} />);

    const link = (await screen.findAllByRole("link", { name: /Summarise this incident report/ }))[0];
    expect(link).toHaveAttribute("title", long);
    expect(link.textContent?.length).toBeLessThanOrEqual(81);
    expect(link).toHaveAttribute("href", "/runs/run-1");

    fireEvent.click(link.closest("tr") as HTMLElement);
    await waitFor(() => expect(router.state.location.pathname).toBe("/runs/run-1"));
  });

  // TR-UX-6
  it("says no runs match, and offers Clear filters, when a filter hides every run", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => makeResponse({ data: [], pagination: { page: 1, page_size: 20, total_items: 0, total_pages: 0 } }),
    });
    const router = createMemoryRouter([{ path: "/", element: <RunsListPage /> }], {
      initialEntries: ["/?tier=opus&status=error"],
    });
    render(<RouterProvider router={router} />);

    expect(await screen.findByText("No runs match these filters.")).toBeInTheDocument();
    expect(screen.queryByText(/No runs yet/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    await waitFor(() => expect(router.state.location.search).toBe(""));
  });

  // TR-UX-7
  it("waits for a pause in typing, makes one request, and replaces the history entry", async () => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => makeResponse() });
    const router = createMemoryRouter([{ path: "/", element: <RunsListPage /> }], { initialEntries: ["/"] });
    render(<RouterProvider router={router} />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    const input = screen.getByLabelText("Use case");
    for (const value of ["s", "su", "sum", "summ"]) {
      fireEvent.change(input, { target: { value } });
    }
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(router.state.location.search).toBe("");

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(String(fetchMock.mock.calls[1][0])).toContain("use_case=summ");
    expect(router.state.historyAction).toBe("REPLACE");
  });

  it("ignores a slow earlier response that arrives after a newer one", async () => {
    let resolveFirst: ((value: unknown) => void) | undefined;
    fetchMock.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveFirst = resolve;
        }),
    );
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => makeResponse({ data: [makeRun({ run_id: "new", use_case: "newer-result" })] }),
    });
    render(
      <MemoryRouter initialEntries={["/"]}>
        <RunsListPage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    fireEvent.change(screen.getByLabelText("Tier"), { target: { value: "sonnet" } });
    expect((await screen.findAllByText("newer-result")).length).toBeGreaterThan(0);

    await act(async () => {
      resolveFirst?.({
        ok: true,
        json: async () => makeResponse({ data: [makeRun({ run_id: "old", use_case: "stale-result" })] }),
      });
    });
    expect(screen.queryByText("stale-result")).not.toBeInTheDocument();
    expect(screen.getAllByText("newer-result").length).toBeGreaterThan(0);
  });

  // TR-UX-4
  it("counts active filters on the phone Filters button", async () => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => makeResponse() });
    render(
      <MemoryRouter initialEntries={["/?tier=opus&status=error"]}>
        <RunsListPage />
      </MemoryRouter>,
    );

    const button = await screen.findByRole("button", { name: "Filters (2)" });
    expect(button).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
  });
});
