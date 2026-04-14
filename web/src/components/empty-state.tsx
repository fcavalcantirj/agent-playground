import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

type EmptyStateProps = {
  icon: LucideIcon;
  heading: string;
  body: string;
  className?: string;
};

/**
 * Reusable empty-state block.
 *
 * Per UI-SPEC Screen 2:
 *  - Icon 48px, muted foreground
 *  - Heading text-xl font-semibold
 *  - Body text-base, muted foreground, max-w-[280px]
 *  - Centered vertically and horizontally in parent
 *  - role="status" so screen readers announce the empty state
 */
export function EmptyState({ icon: Icon, heading, body, className }: EmptyStateProps) {
  return (
    <div
      role="status"
      className={cn(
        "flex w-full flex-col items-center justify-center gap-4 px-4 text-center",
        className,
      )}
    >
      <Icon
        className="size-12 text-muted-foreground"
        aria-hidden="true"
        strokeWidth={1.5}
      />
      <h2 className="text-xl font-semibold text-foreground">{heading}</h2>
      <p className="max-w-[280px] text-base leading-relaxed text-muted-foreground">
        {body}
      </p>
    </div>
  );
}
