"use client";

import { useState, useEffect, useRef } from "react";
import { ApiError } from "@/lib/api";

// ============================================================================
// Server-side Pydantic shape mirrors — keep in sync with:
//   api_server/src/api_server/models/recipes.py::RecipeSummary
//   api_server/src/api_server/models/runs.py::RunRequest + RunResponse
//   api_server/src/api_server/models/errors.py::ErrorEnvelope
// Recipe-schema version field locked by Task 2 via live curl against
// GET /v1/recipes (see /tmp/ap-wire-key.txt) — the Pydantic alias wins
// on the wire; the snake_case form is NOT emitted by the server.
// ============================================================================

export type RecipeSummary = {
  name: string;
  apiVersion?: string;
  display_name?: string | null;
  description?: string | null;
  upstream_version?: string | null;
  image_size_gb?: number | null;
  expected_runtime_seconds?: number | null;
  source_repo?: string | null;
  source_ref?: string | null;
  provider?: string | null;
  pass_if?: string | null;
  license?: string | null;
  maintainer?: string | null;
  verified_models?: string[];  // from smoke.verified_cells[].model (PASS only)
};

export type OpenRouterModel = {
  id: string;
  name: string;
  context_length?: number;
  pricing?: { prompt?: string; completion?: string };
  description?: string;
};

export type RunRequest = {
  recipe_name: string;     // /^[a-z0-9][a-z0-9_-]*$/ , max 64
  prompt?: string | null;  // max 16384
  model: string;           // non-empty, max 128
  no_lint?: boolean;
  no_cache?: boolean;
  metadata?: Record<string, unknown> | null;
  agent_name?: string | null;     // user-facing agent identifier
  personality?: PersonalityId | null;
};

// Personality presets (mirrors api_server/services/personality.py)
export type PersonalityId =
  | "polite-thorough"
  | "concise-neat"
  | "skeptical-critic"
  | "cheerful-helper"
  | "senior-architect"
  | "quick-prototyper";

export const PERSONALITIES: Array<{
  id: PersonalityId;
  label: string;
  description: string;
  emoji: string;
}> = [
  { id: "polite-thorough",  label: "Polite & thorough",  emoji: "📚", description: "Patient, well-structured, explains its reasoning step by step." },
  { id: "concise-neat",     label: "Concise & neat",     emoji: "✂️", description: "Terse, no fluff, code-first, ships the answer in one breath." },
  { id: "skeptical-critic", label: "Skeptical critic",   emoji: "🧐", description: "Challenges assumptions, surfaces edge cases, prefers safety." },
  { id: "cheerful-helper",  label: "Cheerful helper",    emoji: "🌞", description: "Friendly, encouraging, makes onboarding feel low-stakes." },
  { id: "senior-architect", label: "Senior architect",   emoji: "🏛️", description: "Technical depth, considers tradeoffs, names patterns and pitfalls." },
  { id: "quick-prototyper", label: "Quick prototyper",   emoji: "🚀", description: "Ship-fast mindset, MVP energy, willing to cut scope." },
];

export type AgentSummary = {
  id: string;
  name: string;
  recipe_name: string;
  model: string;
  personality?: PersonalityId | null;
  created_at: string;
  last_run_at?: string | null;
  total_runs: number;
  last_verdict?: string | null;
  last_category?: string | null;
  last_run_id?: string | null;
};

export type AgentListResponse = {
  agents: AgentSummary[];
};

export type RunResponse = {
  run_id: string;
  agent_instance_id: string;
  recipe: string;
  model: string;
  prompt: string;
  pass_if?: string | null;
  verdict: string;
  category: string;          // one of: PASS, ASSERT_FAIL, INVOKE_FAIL, BUILD_FAIL,
                             //         PULL_FAIL, CLONE_FAIL, TIMEOUT, LINT_FAIL,
                             //         INFRA_FAIL, STOCHASTIC, SKIP
  detail?: string | null;
  exit_code?: number | null;
  wall_time_s?: number | null;
  filtered_payload?: string | null;
  stderr_tail?: string | null;
  created_at?: string | null;  // ISO-8601
  completed_at?: string | null;
};

export type ErrorResponse = {
  error: {
    type: string;
    code: string;
    category: string | null;
    message: string;
    param: string | null;
    request_id: string;
  };
};

// ============================================================================
// UiError discriminated union — every D-07 error path maps to exactly one kind.
// ============================================================================

export type UiError =
  | { kind: "validation"; field?: string; message: string; requestId?: string }
  | { kind: "rate_limited"; retryAfterSec: number; message: string; requestId?: string }
  | { kind: "unauthorized"; message: string; requestId?: string }
  | { kind: "not_found"; message: string; requestId?: string }
  | { kind: "infra"; message: string; requestId?: string }
  | { kind: "network"; message: string }
  | { kind: "unknown"; message: string; status?: number };

// ============================================================================
// parseApiError — convert any caught exception into a typed UiError.
// Pure function — no module-level state (RESEARCH Pitfall 2: Turbopack HMR).
// ============================================================================

export function parseApiError(err: unknown): UiError {
  if (err instanceof TypeError) {
    return { kind: "network", message: "Could not reach API — check your connection." };
  }
  if (!(err instanceof ApiError)) {
    return { kind: "unknown", message: err instanceof Error ? err.message : "Unknown error" };
  }

  let envelope: ErrorResponse | null = null;
  try { envelope = JSON.parse(err.body) as ErrorResponse; } catch { /* non-JSON body */ }
  const msg = envelope?.error.message ?? err.body ?? `HTTP ${err.status}`;
  const requestId = envelope?.error.request_id;
  const param = envelope?.error.param ?? undefined;

  switch (err.status) {
    case 401:
    case 403:
      return { kind: "unauthorized", message: "Invalid or missing API key", requestId };
    case 404:
      return { kind: "not_found", message: msg, requestId };
    case 422:
      return { kind: "validation", field: param, message: msg, requestId };
    case 429: {
      const retryAfterSec = parseRetryAfter(err.headers.get("Retry-After"));
      return { kind: "rate_limited", retryAfterSec, message: msg, requestId };
    }
    case 500:
    case 502:
    case 503:
      return { kind: "infra", message: msg, requestId };
    default:
      return { kind: "unknown", message: msg, status: err.status };
  }
}

// ============================================================================
// parseRetryAfter — RFC 7231: value is either delta-seconds integer OR HTTP-date.
// MDN: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Retry-After
// Returns a non-negative integer seconds; defaults to 5 if header is missing or unparseable.
// ============================================================================

export function parseRetryAfter(v: string | null): number {
  if (!v) return 5;
  const asInt = Number.parseInt(v, 10);
  if (!Number.isNaN(asInt) && String(asInt) === v.trim()) return Math.max(0, asInt);
  const asDate = Date.parse(v);
  if (!Number.isNaN(asDate)) {
    const deltaMs = asDate - Date.now();
    return Math.max(0, Math.ceil(deltaMs / 1000));
  }
  return 5;
}

// ============================================================================
// useRetryCountdown — ticks down the 429 cooldown; calls onExpire at 0.
// Uses a target-timestamp ref so the countdown survives tab backgrounding.
// onExpire MUST be stable (wrap with useCallback at the call site).
// ============================================================================

export function useRetryCountdown(uiError: UiError | null, onExpire: () => void): number {
  const [remaining, setRemaining] = useState(0);
  const targetRef = useRef<number>(0);

  useEffect(() => {
    if (uiError?.kind !== "rate_limited") {
      setRemaining(0);
      targetRef.current = 0;
      return;
    }
    targetRef.current = Date.now() + uiError.retryAfterSec * 1000;
    setRemaining(uiError.retryAfterSec);

    const t = setInterval(() => {
      const left = Math.max(0, Math.ceil((targetRef.current - Date.now()) / 1000));
      setRemaining(left);
      if (left <= 0) {
        clearInterval(t);
        onExpire();
      }
    }, 1000);

    return () => clearInterval(t);
  }, [uiError, onExpire]);

  return remaining;
}
