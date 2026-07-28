import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { useAuth } from "react-oidc-context";
import { LogIn, ShieldAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { onSessionExpired, rememberReturnTo, type ExpiryReason } from "@/lib/session";

/**
 * What the user sees when their Keycloak session ends under them.
 *
 * Deliberately a blocking modal and not a toast: everything behind it is now
 * unusable — every query will 401 — so offering "carry on" would be a lie. It
 * is also *not* an automatic redirect, which is the tempting shortcut: a
 * redirect fired mid-answer throws away a 60-90 s generation with no
 * explanation. The user decides when to go back, and lands where they left.
 */
const MESSAGE: Record<ExpiryReason, string> = {
  expired: "Your session timed out. Sign in again to continue.",
  "renew-failed": "Your session could not be renewed. Sign in again to continue.",
  "signed-out": "You were signed out — the session ended in Keycloak.",
  unauthorized: "Your session is no longer valid. Sign in again to continue.",
};

export function SessionExpiredDialog() {
  const auth = useAuth();
  const location = useLocation();
  const [reason, setReason] = useState<ExpiryReason | null>(null);

  // Where the user was, read at expiry time rather than at click time: dropping
  // the token flips <ProtectedRoute> to /login in the same tick, so by the time
  // the button is pressed the router already says we are on the login screen.
  const lastProtectedPath = useRef(location.pathname + location.search);
  useEffect(() => {
    if (location.pathname !== "/login") {
      lastProtectedPath.current = location.pathname + location.search;
    }
  }, [location.pathname, location.search]);

  // First reason wins: a stale token typically trips several sources at once
  // (renew fails, then every in-flight query 401s) and the wording of the first
  // one is the accurate diagnosis.
  useEffect(
    () =>
      onSessionExpired((next) => {
        rememberReturnTo(lastProtectedPath.current);
        setReason((current) => current ?? next);
      }),
    [],
  );

  // A fresh sign-in elsewhere in the tree clears the dialog.
  useEffect(() => {
    if (auth.isAuthenticated) setReason(null);
  }, [auth.isAuthenticated]);

  if (!reason) return null;

  return (
    <div
      className="fixed inset-0 z-70 grid place-items-center bg-black/60 p-4"
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="session-expired-title"
    >
      <div className="w-full max-w-sm rounded-lg border border-border bg-card p-6 shadow-lg">
        <div className="flex items-start gap-3">
          <ShieldAlert className="mt-0.5 size-5 shrink-0 text-destructive" />
          <div className="space-y-2">
            <h2 id="session-expired-title" className="text-lg font-semibold">
              Session expired
            </h2>
            <p className="text-sm text-muted-foreground">{MESSAGE[reason]}</p>
            <p className="text-xs text-muted-foreground">
              Unsent answers are lost, but everything already saved is intact.
            </p>
          </div>
        </div>
        <div className="mt-6 flex justify-end">
          <Button onClick={() => void auth.signinRedirect()}>
            <LogIn />
            Sign in again
          </Button>
        </div>
      </div>
    </div>
  );
}
