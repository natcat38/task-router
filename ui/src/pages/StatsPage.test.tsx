import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { StatsPage } from "./StatsPage";
import type { StatsResponse } from "../api/types";

function makeStats(overrides: Partial<StatsResponse> = {}): StatsResponse {
  return {
    n_requests: 100,
    by_tier: { local: 70, sonnet: 25, opus: 5 },
    saved_pct_excl_judge: 82.4,
    saved_pct_incl_judge: 74.1,
    price_basis: "api_list_prices_no_money_changed_hands",
    ...overrides,
  };
}

describe("StatsPage", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders both saved figures, the honesty label, and the by-tier breakdown", async () => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => makeStats() });

    render(
      <MemoryRouter>
        <StatsPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("82.4%")).toBeInTheDocument();
    expect(screen.getByText("74.1%")).toBeInTheDocument();
    expect(screen.getByText(/Saved, excluding judge cost/)).toBeInTheDocument();
    expect(screen.getByText(/Saved, including judge cost/)).toBeInTheDocument();
    expect(
      screen.getByText(/Savings at API list prices — no money changed hands/),
    ).toBeInTheDocument();

    expect(screen.getByText("100")).toBeInTheDocument();
    expect(screen.getByText(/70 \(70%\)/)).toBeInTheDocument();
    expect(screen.getByText(/25 \(25%\)/)).toBeInTheDocument();
    expect(screen.getByText(/5 \(5%\)/)).toBeInTheDocument();
  });

  it("shows the empty-state copy when there are no completed runs", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => makeStats({ n_requests: 0, by_tier: { local: 0, sonnet: 0, opus: 0 } }),
    });

    render(
      <MemoryRouter>
        <StatsPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText(/No completed runs yet/)).toBeInTheDocument();
  });

  it("shows the unreachable-API copy on a network failure", async () => {
    fetchMock.mockRejectedValue(new TypeError("network down"));

    render(
      <MemoryRouter>
        <StatsPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText(/Couldn't reach the router API/)).toBeInTheDocument();
  });
});
