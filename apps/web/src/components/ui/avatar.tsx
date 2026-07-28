import { cn } from "@/lib/utils";

/** Initials avatar — no image source in this app, so we render a colored badge. */
export function Avatar({
  name,
  className,
}: {
  name: string;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex size-9 shrink-0 select-none items-center justify-center rounded-full bg-primary text-sm font-medium text-primary-foreground",
        className,
      )}
      aria-hidden
    >
      {initials(name)}
    </span>
  );
}

function initials(name: string): string {
  const parts = name.trim().split(/[\s@._-]+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}
