import { describe, expect, it, vi } from "vitest";
import {
  ApiError,
  createDiscovery,
  safeWebsite,
  searchEntities,
  sendFeedback,
} from "../api";
describe("API boundary", () => {
  it("allows only credential-free HTTP(S) external sites", () => {
    expect(safeWebsite("https://example.org/path")).toBe(
      "https://example.org/path",
    );
    for (const url of [
      "javascript:alert(1)",
      "data:text/html,hi",
      "//example.org",
      "https://secret:password@example.org",
      "",
      null,
    ])
      expect(safeWebsite(url)).toBeNull();
  });
  it("encodes search data without hard-coding a browser origin", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(JSON.stringify({ items: [] })));
    await searchEntities("A & B", "movie");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/entities/search?q=A+%26+B&category=movie",
      expect.objectContaining({ credentials: "same-origin" }),
    );
  });
  it("does not send an intent on the non-model path", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response("{}"));
    await createDiscovery(
      [{ id: "id", name: "Bowie", category: "artist", tags: [] }],
      "curious",
      "  ",
      "request-key",
    );
    const init = fetchMock.mock.calls[0][1]!;
    expect(JSON.parse(init.body as string)).toEqual({
      seed_ids: ["id"],
      level: "curious",
    });
    expect(init.headers).toEqual({
      "Content-Type": "application/json",
      "Idempotency-Key": "request-key",
    });
  });
  it("sends trimmed optional intent only when asked", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response("{}"));
    await createDiscovery([], "wild", " Quiet evening ", "key");
    expect(
      JSON.parse(fetchMock.mock.calls[0][1]!.body as string).intent,
    ).toEqual({
      text: "Quiet evening",
      categories: ["artist", "movie", "book"],
    });
  });
  it("sanitizes provider errors instead of displaying raw response details", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: {
            code: "agent_rate_limit",
            debug: "private provider details",
          },
        }),
        { status: 429 },
      ),
    );
    await expect(sendFeedback("discovery", "entity", "save")).rejects.toThrow(
      "The planner has reached its limit.",
    );
  });
  it("turns network failures into a usable message", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(
      new Error("private network detail"),
    );
    await expect(searchEntities("Bowie", "artist")).rejects.toBeInstanceOf(
      ApiError,
    );
  });
  it("keeps caller cancellation separate from a service error", async () => {
    const controller = new AbortController();
    controller.abort();
    vi.spyOn(globalThis, "fetch").mockRejectedValue(
      new DOMException("Aborted", "AbortError"),
    );
    await expect(
      searchEntities("Bowie", "artist", controller.signal),
    ).rejects.toHaveProperty("name", "AbortError");
  });
});
