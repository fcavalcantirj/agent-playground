// Thin fetch wrapper for the Go API.
// Always sends cookies (session lives in an HttpOnly cookie set by the Go API).
// The Next.js dev server proxies `/api/*` to the Go API via next.config.ts rewrites.

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

export class ApiError extends Error {
  status: number;
  body: string;

  constructor(status: number, body: string, message?: string) {
    super(message ?? `API error ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {}
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...(init.headers ?? {}),
    },
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new ApiError(res.status, text);
  }

  // Empty responses (e.g. 204) are safe to return as null.
  const contentType = res.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    return null as T;
  }
  return (await res.json()) as T;
}

export function apiGet<T = unknown>(path: string): Promise<T> {
  return request<T>(path, { method: "GET" });
}

export function apiPost<T = unknown>(
  path: string,
  body?: unknown
): Promise<T> {
  return request<T>(path, {
    method: "POST",
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}

export function apiDelete<T = unknown>(path: string): Promise<T> {
  return request<T>(path, { method: "DELETE" });
}

// Shape of the session returned from GET /api/me.
// Keep this aligned with the Go handler in Plan 01-02.
export type SessionUser = {
  id: string;
  email?: string;
  display_name: string;
  avatar_url?: string;
  provider?: string;
};
