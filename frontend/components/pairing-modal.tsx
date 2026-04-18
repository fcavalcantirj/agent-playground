"use client";

import type React from "react";
import { useEffect, useRef, useState } from "react";
import { Loader2, X } from "lucide-react";

import { apiPost, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type {
  AgentChannelPairRequest,
  AgentChannelPairResponse,
} from "@/lib/api-types";

// G4 (spike-10): openclaw's pair approve blocks for ~60s while the CLI
// cold-boots inside the container. 90s matches the server-side
// docker-exec timeout in routes/agent_lifecycle.py. The modal discloses
// the wait up-front, ticks an elapsed-time counter while in-flight, and
// disables the Approve button until the first request returns so the
// user can't pile up concurrent cold-boot invocations.
const PAIR_FETCH_TIMEOUT_MS = 90_000;

export function PairingModal({
  agentId,
  channel,
  bearer,
  onClose,
}: {
  agentId: string;
  channel: string;
  bearer: string;
  onClose: () => void;
}) {
  const [code, setCode] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [elapsedS, setElapsedS] = useState(0);
  const [result, setResult] = useState<AgentChannelPairResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const elapsedTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Tick an elapsed-time counter while the request is in flight so the
  // user has feedback during the ~60s wait.
  useEffect(() => {
    if (submitting) {
      setElapsedS(0);
      const t0 = Date.now();
      elapsedTimerRef.current = setInterval(() => {
        setElapsedS(Math.round((Date.now() - t0) / 1000));
      }, 500);
    } else if (elapsedTimerRef.current) {
      clearInterval(elapsedTimerRef.current);
      elapsedTimerRef.current = null;
    }
    return () => {
      if (elapsedTimerRef.current) {
        clearInterval(elapsedTimerRef.current);
        elapsedTimerRef.current = null;
      }
    };
  }, [submitting]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!code.trim() || submitting) return; // block concurrent submits
    setSubmitting(true);
    setError(null);

    const controller = new AbortController();
    const timeoutHandle = setTimeout(
      () => controller.abort(),
      PAIR_FETCH_TIMEOUT_MS,
    );

    try {
      const body: AgentChannelPairRequest = { code: code.trim() };
      const res = await apiPost<AgentChannelPairResponse>(
        `/api/v1/agents/${agentId}/channels/${channel}/pair`,
        body,
        { Authorization: `Bearer ${bearer}` },
        { signal: controller.signal },
      );
      setResult(res);
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") {
        setError("Pairing request timed out after 90s.");
      } else if (e instanceof ApiError) {
        // Try to surface the server's error envelope message.
        try {
          const env = JSON.parse(e.body);
          setError(env?.error?.message ?? `HTTP ${e.status}`);
        } catch {
          setError(`HTTP ${e.status}`);
        }
      } else {
        setError(e instanceof Error ? e.message : "pair failed");
      }
    } finally {
      clearTimeout(timeoutHandle);
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="pairing-title"
    >
      <div className="relative w-full max-w-md rounded-2xl border border-border/50 bg-card p-6 shadow-2xl">
        <button
          type="button"
          onClick={onClose}
          className="absolute right-4 top-4 rounded-lg p-2 text-muted-foreground transition-colors hover:bg-muted disabled:opacity-50"
          aria-label="Close"
          disabled={submitting}
        >
          <X className="size-4" />
        </button>

        <h2 id="pairing-title" className="text-xl font-semibold text-foreground">
          Approve the pairing code
        </h2>
        <p className="mt-2 text-sm text-foreground/70">
          DM your bot once. It will reply with a short code. Paste it here to
          finish pairing.
        </p>
        <p className="mt-2 text-xs text-muted-foreground">
          Approval takes up to 60 seconds for openclaw. Please wait after you
          click Approve.
        </p>

        {result ? (
          <div
            className={cn(
              "mt-5 rounded-xl border p-4",
              result.exit_code === 0
                ? "border-emerald-500/40 bg-emerald-500/10"
                : "border-rose-500/40 bg-rose-500/10",
            )}
          >
            <div className="text-sm font-medium text-foreground">
              {result.exit_code === 0
                ? "✓ Paired"
                : `✗ exit ${result.exit_code}`}
              {typeof result.wall_s === "number" && (
                <span className="ml-2 text-xs text-muted-foreground">
                  ({result.wall_s.toFixed(1)}s)
                </span>
              )}
            </div>
            {result.stdout_tail && (
              <pre className="mt-2 max-h-48 overflow-auto rounded bg-black/40 p-2 text-xs font-mono text-white/80">
                {result.stdout_tail}
              </pre>
            )}
            {result.stderr_tail && (
              <pre className="mt-2 max-h-24 overflow-auto rounded bg-rose-950/60 p-2 text-xs font-mono text-rose-200">
                {result.stderr_tail}
              </pre>
            )}
            <Button className="mt-4 w-full" onClick={onClose}>
              Done
            </Button>
          </div>
        ) : (
          <form onSubmit={onSubmit} className="mt-5 space-y-4">
            <div>
              <Label htmlFor="pair-code">Pairing code</Label>
              <Input
                id="pair-code"
                value={code}
                onChange={(e) =>
                  // Server regex is ^[A-Za-z0-9]+$ — strip anything else
                  // client-side so paste-and-submit works with whitespace.
                  setCode(e.target.value.replace(/[^A-Za-z0-9]/g, ""))
                }
                autoFocus
                autoComplete="off"
                autoCorrect="off"
                autoCapitalize="off"
                spellCheck={false}
                placeholder="4–8 chars, from the bot's DM"
                maxLength={16}
                className="mt-2 h-12 font-mono text-lg tracking-widest"
                disabled={submitting}
              />
            </div>
            {error && <p className="text-sm text-rose-400">{error}</p>}
            <div className="flex gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={onClose}
                disabled={submitting}
                className="flex-1"
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={!code.trim() || submitting}
                className="flex-1"
              >
                {submitting && <Loader2 className="size-4 animate-spin" />}
                {submitting ? `Approving… ${elapsedS}s` : "Approve"}
              </Button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
