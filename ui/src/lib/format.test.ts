import { describe, expect, it } from "vitest";
import { formatRelative, requestSnippet } from "./format";

describe("requestSnippet", () => {
  it("collapses whitespace, caps at 80 characters, and names an empty request", () => {
    expect(requestSnippet("a\n\n  b")).toBe("a b");
    expect(requestSnippet("x".repeat(200))).toBe(`${"x".repeat(80)}…`);
    expect(requestSnippet("   ")).toBe("(no request text)");
  });
});

describe("formatRelative", () => {
  const now = Date.parse("2026-09-18T12:00:00Z");
  it("uses minutes, hours and days, and passes unparseable input through", () => {
    expect(formatRelative("2026-09-18T11:59:30Z", now)).toBe("just now");
    expect(formatRelative("2026-09-18T11:55:00Z", now)).toBe("5m ago");
    expect(formatRelative("2026-09-18T09:00:00Z", now)).toBe("3h ago");
    expect(formatRelative("2026-09-16T12:00:00Z", now)).toBe("2d ago");
    expect(formatRelative("nope", now)).toBe("nope");
  });
});
