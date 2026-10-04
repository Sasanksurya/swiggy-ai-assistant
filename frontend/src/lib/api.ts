import type { ChatResponse, PlatformInfo } from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** The backend answers errors in two shapes: FastAPI validation (list) and platform errors (object). */
export function describeError(body: unknown, status: number): { message: string; code?: string } {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (Array.isArray(detail)) {
    return { message: "That message couldn't be sent. Try a shorter or different message.", code: "validation" };
  }
  if (typeof detail === "string") return { message: detail };
  const err = (detail as { error?: { code?: string; message?: string } } | undefined)?.error;
  if (err?.message) return { message: err.message, code: err.code };
  return { message: `Something went wrong (error ${status}).` };
}

export function isChatResponse(x: unknown): x is ChatResponse {
  if (!x || typeof x !== "object") return false;
  const r = x as Record<string, unknown>;
  return (
    typeof r.session_id === "string" &&
    typeof r.reply === "string" &&
    typeof r.intent === "string" &&
    typeof r.synthetic === "boolean" &&
    (r.source === "mock" || r.source === "swiggy") &&
    !!r.cards && typeof r.cards === "object" &&
    Array.isArray(r.tool_calls)
  );
}

async function request(path: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(path, init);
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new ApiError("Can't reach Sarah's server. Check that the backend is running.", 0, "network");
  }
}

async function parse(res: Response): Promise<unknown> {
  const text = await res.text();
  try {
    return text ? JSON.parse(text) : null;
  } catch {
    return null;
  }
}

export async function sendChat(message: string, sessionId?: string, signal?: AbortSignal): Promise<ChatResponse> {
  const res = await request("/api/chat", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(sessionId ? { message, session_id: sessionId } : { message }),
    signal,
  });
  const body = await parse(res);
  if (!res.ok) {
    const { message: m, code } = describeError(body, res.status);
    throw new ApiError(m, res.status, code);
  }
  if (!isChatResponse(body)) throw new ApiError("Sarah sent a reply the app couldn't read.", 502, "bad_response");
  return body;
}

export async function getPlatformInfo(signal?: AbortSignal): Promise<PlatformInfo> {
  const res = await request("/api/platform/info", { signal });
  const body = await parse(res);
  if (!res.ok || !body || typeof (body as PlatformInfo).synthetic !== "boolean") {
    const { message, code } = describeError(body, res.status);
    throw new ApiError(message, res.status, code);
  }
  return body as PlatformInfo;
}

export async function resetSession(sessionId: string): Promise<void> {
  const res = await request(`/api/chat/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
  if (!res.ok && res.status !== 204) throw new ApiError("Couldn't start a new conversation.", res.status);
}
