"use client";

import { useState, type RefObject } from "react";
import { Copy, Check } from "lucide-react";

import type { RunResponse } from "@/lib/api-types";
import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Accordion,
  AccordionItem,
  AccordionTrigger,
  AccordionContent,
} from "@/components/ui/accordion";

/**
 * Verdict-color map — keyed by RunResponse.category (the fine-grained enum from
 * api_server/src/api_server/models/runs.py::Category).
 *
 * PASS       → emerald (success)
 * FAIL-ish   → destructive (red) — 7 categories: ASSERT_FAIL, INVOKE_FAIL,
 *              BUILD_FAIL, PULL_FAIL, CLONE_FAIL, TIMEOUT, LINT_FAIL
 * INFRA_FAIL → amber (distinct from FAIL — infrastructure, not agent logic)
 * STOCHASTIC → yellow (warning)
 * SKIP       → slate (neutral)
 *
 * Unknown categories fall through to the muted default.
 */
const CATEGORY_BADGE_CLASS: Record<string, string> = {
  PASS:        "bg-emerald-600 text-white border-transparent",
  ASSERT_FAIL: "bg-destructive text-destructive-foreground border-transparent",
  INVOKE_FAIL: "bg-destructive text-destructive-foreground border-transparent",
  BUILD_FAIL:  "bg-destructive text-destructive-foreground border-transparent",
  PULL_FAIL:   "bg-destructive text-destructive-foreground border-transparent",
  CLONE_FAIL:  "bg-destructive text-destructive-foreground border-transparent",
  TIMEOUT:     "bg-destructive text-destructive-foreground border-transparent",
  LINT_FAIL:   "bg-destructive text-destructive-foreground border-transparent",
  INFRA_FAIL:  "bg-amber-500 text-white border-transparent",
  STOCHASTIC:  "bg-yellow-500 text-black border-transparent",
  SKIP:        "bg-slate-400 text-white border-transparent",
};

/**
 * Pure prop-driven display of a POST /v1/runs response. No network, no side-effects
 * beyond the copy-button feedback timer.
 *
 * The cardRef prop is passed from the parent <PlaygroundForm> so focus can be
 * moved to the card when a verdict renders (UI-SPEC §A11y bullet 2). It is
 * optional so the component is also usable in isolation (e.g., future storybook).
 */
export function RunResultCard({
  verdict,
  cardRef,
}: {
  verdict: RunResponse;
  cardRef?: RefObject<HTMLDivElement | null>;
}) {
  const [copied, setCopied] = useState(false);

  async function copyRunId() {
    try {
      await navigator.clipboard.writeText(verdict.run_id);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard API can fail on insecure contexts or when the user denies
      // permission. Silently leave the icon as Copy — screen readers still
      // get the "Copy run_id" aria-label. No toast (D-02: minimum decoration).
    }
  }

  const stderrLineCount = verdict.stderr_tail?.split("\n").length ?? 0;
  const badgeClass =
    CATEGORY_BADGE_CLASS[verdict.category] ?? "bg-muted text-foreground border-transparent";
  const completedAt = verdict.completed_at ?? verdict.created_at ?? null;

  return (
    <Card
      ref={cardRef}
      role="status"
      aria-live="polite"
      tabIndex={-1}
      className="p-8"
    >
      <CardContent className="flex flex-col gap-6 p-0">
        {/* Header row: verdict badge + category pill + timestamp */}
        <div className="flex items-center gap-3">
          <Badge className={cn("px-3 py-1 text-sm font-bold uppercase tracking-wider", badgeClass)}>
            {verdict.verdict}
          </Badge>
          <Badge variant="outline" className="border-border/70 bg-muted/60 px-2.5 py-1 font-mono text-xs text-foreground/90">
            {verdict.category}
          </Badge>
          {completedAt && (
            <span className="ml-auto font-mono text-sm text-foreground/70">
              {new Date(completedAt).toLocaleTimeString()}
            </span>
          )}
        </div>

        {/* Metadata grid */}
        <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-base">
          <dt className="font-mono text-sm uppercase tracking-wider text-foreground/60">exit_code</dt>
          <dd className="font-mono text-foreground">{verdict.exit_code ?? "—"}</dd>

          <dt className="font-mono text-sm uppercase tracking-wider text-foreground/60">wall_time</dt>
          <dd className="font-mono text-foreground">
            {verdict.wall_time_s != null ? `${verdict.wall_time_s.toFixed(2)}s` : "—"}
          </dd>

          <dt className="font-mono text-sm uppercase tracking-wider text-foreground/60">run_id</dt>
          <dd className="flex items-center gap-2">
            <code className="font-mono text-sm text-foreground/90">{verdict.run_id}</code>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={copyRunId}
              aria-label="Copy run_id"
              className="size-8"
            >
              {copied ? (
                <Check className="size-4" aria-hidden="true" />
              ) : (
                <Copy className="size-4" aria-hidden="true" />
              )}
            </Button>
          </dd>
        </dl>

        {verdict.detail && (
          <p className="text-base leading-relaxed text-foreground/80">{verdict.detail}</p>
        )}

        {(verdict.prompt || verdict.filtered_payload || verdict.pass_if) && (
          <div className="rounded-lg border border-border/60 bg-muted/30 p-4">
            <p className="mb-3 font-mono text-sm uppercase tracking-wider text-foreground/60">
              smoke check
            </p>
            <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-base">
              {verdict.pass_if && (
                <>
                  <dt className="font-mono text-sm uppercase tracking-wider text-foreground/60">
                    pass_if
                  </dt>
                  <dd className="font-mono text-foreground">{verdict.pass_if}</dd>
                </>
              )}
              {verdict.prompt && (
                <>
                  <dt className="font-mono text-sm uppercase tracking-wider text-foreground/60">
                    prompt
                  </dt>
                  <dd className="text-foreground/90 whitespace-pre-wrap break-words">
                    {verdict.prompt}
                  </dd>
                </>
              )}
              {verdict.filtered_payload && (
                <>
                  <dt className="font-mono text-sm uppercase tracking-wider text-foreground/60">
                    reply
                  </dt>
                  <dd className="text-foreground/85 whitespace-pre-wrap break-words">
                    {verdict.filtered_payload.length > 600
                      ? `${verdict.filtered_payload.slice(0, 600)}…`
                      : verdict.filtered_payload}
                  </dd>
                </>
              )}
            </dl>
          </div>
        )}

        <Accordion
          type="single"
          collapsible
          defaultValue={verdict.verdict !== "PASS" ? "stderr" : undefined}
        >
          <AccordionItem value="stderr" className="border-t border-border/60">
            <AccordionTrigger className="py-4 text-base font-semibold text-foreground hover:no-underline">
              stderr tail ({stderrLineCount} lines)
            </AccordionTrigger>
            <AccordionContent>
              <pre className="max-h-96 overflow-auto rounded-lg bg-muted/60 p-4 font-mono text-sm leading-relaxed text-foreground/85 whitespace-pre-wrap break-words">
                {verdict.stderr_tail || "(no output)"}
              </pre>
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      </CardContent>
    </Card>
  );
}
