import { RefreshCw } from "lucide-react";

import { Button } from "./button";
import { cn } from "@/lib/utils";

/**
 * The two panel states every list and table in the app needs, written once.
 *
 * Before this, each feature spelled its own `<p className="text-destructive">`
 * and none of them offered a way out: on a failed fetch the only recovery was a
 * full page reload, which on this stack means re-running the OIDC session check
 * as well. `ErrorState` takes the query's `refetch` so a transient failure —
 * the API container still warming up, a dropped request — costs one click.
 */
export function ErrorState({
  title = "Could not load this.",
  message,
  onRetry,
  retrying = false,
  className,
}: {
  title?: string;
  message?: string;
  onRetry?: () => void;
  retrying?: boolean;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm",
        className,
      )}
    >
      <div className="space-y-1">
        <p className="font-medium text-destructive">{title}</p>
        {message && <p className="text-muted-foreground">{message}</p>}
      </div>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry} disabled={retrying}>
          <RefreshCw className={cn(retrying && "animate-spin")} />
          {retrying ? "Retrying…" : "Try again"}
        </Button>
      )}
    </div>
  );
}

/** Nothing to show yet — an explanation plus, ideally, the next action. */
export function EmptyState({
  icon: Icon,
  title,
  hint,
  className,
}: {
  icon?: React.ComponentType<{ className?: string }>;
  title: string;
  hint?: string;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center gap-2 py-8 text-center text-muted-foreground",
        className,
      )}
    >
      {Icon && <Icon className="size-6" />}
      <p className="text-sm font-medium">{title}</p>
      {hint && <p className="text-xs">{hint}</p>}
    </div>
  );
}
