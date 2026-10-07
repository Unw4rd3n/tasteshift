import type { Category, Discovery, Entity, Feedback, Level } from "./types";

export class ApiError extends Error {
  constructor(public code: string) {
    super(errorMessage(code));
  }
}
export function errorMessage(code: string): string {
  const known: Record<string, string> = {
    provider_not_configured:
      "Discovery is not connected yet. You can still explore the preview.",
    agent_not_configured:
      "The experience planner is unavailable. Try without an intention.",
    agent_rate_limit:
      "The planner has reached its limit. Try without an intention, or come back later.",
    agent_busy: "The planner is busy. Please try again in a moment.",
    storage_unavailable: "Your session could not be saved. Please try again.",
    timeout: "This is taking longer than expected. Please try again.",
    network:
      "We could not reach the discovery service. Check your connection and try again.",
    expired:
      "This saved discovery belongs to an expired session. Make a new discovery to give feedback.",
    invalid:
      "Some interests could not be resolved. Search and select them again.",
  };
  return (
    known[code] ||
    "The discovery service is unavailable right now. Please try again."
  );
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  signal?: AbortSignal,
): Promise<T> {
  const controller = new AbortController();
  const abort = () => controller.abort(signal?.reason);
  signal?.addEventListener("abort", abort, { once: true });
  if (signal?.aborted) abort();
  const timer = window.setTimeout(() => controller.abort("timeout"), 65000);
  try {
    const response = await fetch(`/api${path}`, {
      ...init,
      credentials: "same-origin",
      signal: controller.signal,
    });
    let data: any;
    try {
      data = await response.json();
    } catch {
      throw new ApiError("unavailable");
    }
    if (!response.ok) {
      const code =
        data?.detail?.code ||
        (response.status === 404
          ? "expired"
          : response.status === 422
            ? "invalid"
            : "unavailable");
      throw new ApiError(code);
    }
    return data as T;
  } catch (error) {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    if (controller.signal.aborted) throw new ApiError("timeout");
    if (error instanceof ApiError) throw error;
    throw new ApiError("network");
  } finally {
    window.clearTimeout(timer);
    signal?.removeEventListener("abort", abort);
  }
}

export async function searchEntities(
  query: string,
  category: Category,
  signal?: AbortSignal,
): Promise<Entity[]> {
  const response = await request<{ items: Entity[] }>(
    `/entities/search?${new URLSearchParams({ q: query, category })}`,
    {},
    signal,
  );
  return response.items;
}
export function createDiscovery(
  seeds: Entity[],
  level: Level,
  intention: string,
  key: string,
  signal?: AbortSignal,
) {
  return request<Discovery>(
    "/discoveries",
    {
      method: "POST",
      headers: { "Content-Type": "application/json", "Idempotency-Key": key },
      body: JSON.stringify({
        seed_ids: seeds.map((seed) => seed.id),
        level,
        ...(intention.trim()
          ? {
              intent: {
                text: intention.trim(),
                categories: ["artist", "movie", "book"],
              },
            }
          : {}),
      }),
    },
    signal,
  );
}
export function sendFeedback(
  discoveryId: string,
  entityId: string,
  action: Feedback,
) {
  return request<{ status: string }>(
    `/discoveries/${encodeURIComponent(discoveryId)}/feedback`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ entity_id: entityId, action }),
    },
  );
}
export function safeWebsite(value?: string | null): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) &&
      !url.username &&
      !url.password
      ? url.href
      : null;
  } catch {
    return null;
  }
}
