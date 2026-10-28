import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusChip } from "./StatusChip";
import { Timestamp } from "./Timestamp";

describe("StatusChip", () => {
  it("shows ok as quiet text and error as a chip with an icon and the word", () => {
    const { container, rerender } = render(<StatusChip status="ok" />);
    expect(screen.getByText("ok")).toBeInTheDocument();
    expect(container.querySelector("svg")).toBeNull();

    rerender(<StatusChip status="error" />);
    expect(screen.getByText("error")).toBeInTheDocument();
    expect(container.querySelector("svg")).not.toBeNull();
  });
});

describe("Timestamp", () => {
  it("renders local time with the UTC instant in the title, and falls back to the raw string", () => {
    const { container, rerender } = render(<Timestamp iso="2026-09-18T20:45:00+00:00" />);
    const time = container.querySelector("time");
    expect(time).toHaveAttribute("title", "2026-09-18T20:45:00.000Z (UTC)");

    rerender(<Timestamp iso="not a date" />);
    expect(container.querySelector("time")).toBeNull();
    expect(screen.getByText("not a date")).toBeInTheDocument();
  });
});
