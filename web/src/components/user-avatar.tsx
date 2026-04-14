import { cn } from "@/lib/utils";

type UserAvatarProps = {
  displayName: string;
  avatarUrl?: string;
  className?: string;
};

/**
 * 32px circular avatar with initials fallback.
 *
 * Per UI-SPEC Screen 2: 32px circle, initials fallback, muted background,
 * displayName in a native title tooltip for screen-reader and hover hint.
 */
export function UserAvatar({ displayName, avatarUrl, className }: UserAvatarProps) {
  const initial = displayName.trim().charAt(0).toUpperCase() || "?";

  return (
    <div
      title={displayName}
      aria-label={`Signed in as ${displayName}`}
      className={cn(
        "flex size-8 shrink-0 items-center justify-center overflow-hidden rounded-full bg-muted text-sm font-medium text-muted-foreground ring-1 ring-border",
        className,
      )}
    >
      {avatarUrl ? (
        // Avatar URLs come from OAuth providers (Google/GitHub). Using
        // next/image here would require allow-listing every provider host
        // and adds no measurable LCP benefit for a 32px avatar.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={avatarUrl}
          alt={displayName}
          className="size-full object-cover"
          referrerPolicy="no-referrer"
        />
      ) : (
        <span aria-hidden="true">{initial}</span>
      )}
    </div>
  );
}
