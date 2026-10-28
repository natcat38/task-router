import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getRuns, postReplay } from "./client";

describe("api client headers", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  // TR-UX-17: a Content-Type header on a GET forces a CORS preflight before every read.
  it("sends no Content-Type on a GET, so the browser skips the preflight", async () => {
    await getRuns({ page: 1 });
    const init = fetchMock.mock.calls[0][1] as RequestInit | undefined;
    expect(init?.headers).toBeUndefined();
  });

  it("still sends Content-Type on a POST with a body", async () => {
    await postReplay({ source_run_id: "r1", forced_tier: "opus" });
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.headers).toEqual({ "Content-Type": "application/json" });
  });
});
