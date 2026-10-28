import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
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

describe("AppShell mobile bar", () => {
  function renderShell() {
    return render(
      <MemoryRouter>
        <AppShell>
          <p>page content</p>
        </AppShell>
      </MemoryRouter>,
    );
  }

  // TR-UX-2: the bar and the rail stay pinned on long pages.
  it("pins the mobile bar and the desktop rail", () => {
    const { container } = renderShell();
    const bar = container.querySelector("header")?.parentElement;
    expect(bar?.className).toContain("sticky");
    expect(bar?.className).toContain("top-0");
    expect(container.querySelector("aside")?.className).toContain("md:sticky");
  });

  // TR-UX-12
  it("closes the menu on Escape, on a tap outside, and on a route change", () => {
    renderShell();
    const menu = screen.getByRole("button", { name: "Menu" });

    fireEvent.click(menu);
    expect(screen.getByRole("button", { name: "Close" })).toHaveAttribute("aria-expanded", "true");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.getByRole("button", { name: "Menu" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByRole("button", { name: "Menu" })).toHaveFocus();

    fireEvent.click(screen.getByRole("button", { name: "Menu" }));
    fireEvent.pointerDown(screen.getByText("page content"));
    expect(screen.getByRole("button", { name: "Menu" })).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(screen.getByRole("button", { name: "Menu" }));
    fireEvent.click(screen.getAllByRole("link", { name: "Stats" })[0]);
    expect(screen.getByRole("button", { name: "Menu" })).toHaveAttribute("aria-expanded", "false");
  });
});
