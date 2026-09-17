import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AppShell } from "./AppShell";

describe("AppShell", () => {
  it("renders the primary nav links and the tier legend", () => {
    render(
      <MemoryRouter>
        <AppShell>
          <p>page content</p>
        </AppShell>
      </MemoryRouter>,
    );

    const nav = screen.getByRole("navigation", { name: "Primary" });
    expect(nav).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Runs" })[0]).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Stats" })[0]).toBeInTheDocument();

    // The tier legend -- the app's one signature element -- is always visible.
    expect(screen.getAllByText("local")[0]).toBeInTheDocument();
    expect(screen.getAllByText("sonnet")[0]).toBeInTheDocument();
    expect(screen.getAllByText("opus")[0]).toBeInTheDocument();

    expect(screen.getByText("page content")).toBeInTheDocument();
  });
});
