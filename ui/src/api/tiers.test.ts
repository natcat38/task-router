import { describe, expect, it } from "vitest";
import { isTier } from "./tiers";

describe("isTier", () => {
  it("accepts the three known tiers", () => {
    expect(isTier("local")).toBe(true);
    expect(isTier("sonnet")).toBe(true);
    expect(isTier("opus")).toBe(true);
  });

  it("rejects anything else", () => {
    expect(isTier("gpt4")).toBe(false);
    expect(isTier(null)).toBe(false);
    expect(isTier(undefined)).toBe(false);
  });
});
