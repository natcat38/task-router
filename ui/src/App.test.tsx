import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { App } from "./App";

describe("App routes", () => {
  // TR-UX-11
  it("renders a not-found page with a way back, and titles the tab", () => {
    render(
      <MemoryRouter initialEntries={["/nope"]}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByText("There is no page at this address.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to Runs" })).toHaveAttribute("href", "/");
    expect(document.title).toBe("Not found | task-router");
  });

  it("titles the runs list and the stats page", async () => {
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));
    const { unmount } = render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );
    expect(document.title).toBe("Runs | task-router");
    unmount();

    render(
      <MemoryRouter initialEntries={["/stats"]}>
        <App />
      </MemoryRouter>,
    );
    expect(document.title).toBe("Stats | task-router");
    vi.unstubAllGlobals();
  });
});
