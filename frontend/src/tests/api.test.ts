import { describe, expect, it, vi } from "vitest";
import { getHealth, getReadiness, request } from "../lib/api";

describe("API response contracts", () => {
  it("explains unreadable proxy responses without exposing parser internals", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", {status: 500})));
    await expect(request("/companies")).rejects.toThrow("Check that the API and database are running");
  });
  it("rejects invalid health payloads instead of reporting a working service", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(
            JSON.stringify({ status: "ok", reporting_year: "2025" }),
          ),
        ),
    );
    await expect(getHealth()).rejects.toThrow("valid health response");
  });

  it("accepts a typed 503 readiness result", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(
            JSON.stringify({
              status: "not_ready",
              database: "unavailable",
              detail: "Start PostgreSQL.",
            }),
            { status: 503 },
          ),
        ),
    );
    await expect(getReadiness()).resolves.toMatchObject({
      status: "not_ready",
      database: "unavailable",
    });
  });

  it("rejects contradictory status and database indicators", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(
            JSON.stringify({
              status: "ready",
              database: "unavailable",
              detail: "Invalid result.",
            }),
          ),
        ),
    );
    await expect(getReadiness()).rejects.toThrow("valid readiness response");
  });
});
