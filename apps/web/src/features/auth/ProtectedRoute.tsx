import { useEffect, useRef, useState } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "react-oidc-context";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { takeReturnTo } from "@/lib/session";

/**
 * Gate for authenticated routes. Renders the nested routes only for a signed-in
 * user; otherwise it bounces to /login, remembering where the user was headed so
 * LoginPage can send them back after Keycloak returns.
 *
 * The OIDC redirect callback is processed by <AuthProvider> before any route
 * renders, so by the time we get here `isLoading` reliably means "still checking
 * the session", not "mid-callback".
 */
export function ProtectedRoute() {
  const auth = useAuth();
  const location = useLocation();
  const [returnTo, setReturnTo] = useState<string | null>(null);
  const consumed = useRef(false);

  /**
   * Land the user back where the session died.
   *
   * The OIDC `redirect_uri` is pinned to the app root, so a re-login always
   * arrives at "/". The path was stashed at expiry time; consume it exactly
   * once — the ref guard matters because StrictMode runs this effect twice in
   * dev and the second read would come back empty.
   */
  useEffect(() => {
    // Losing the session re-arms the guard: this component stays mounted across
    // an expire/re-login cycle (it just renders a redirect), so without the
    // reset only the first expiry of a page's life would restore its path.
    if (!auth.isAuthenticated) {
      consumed.current = false;
      setReturnTo(null);
      return;
    }
    if (!consumed.current) {
      consumed.current = true;
      setReturnTo(takeReturnTo());
    }
  }, [auth.isAuthenticated]);

  if (auth.isLoading) {
    return (
      <div className="grid min-h-dvh place-items-center text-muted-foreground">
        <div className="flex items-center gap-2 text-sm">
          <Loader2 className="size-4 animate-spin" />
          Checking your session…
        </div>
      </div>
    );
  }

  // A failed session check is not the same as "not signed in": silently
  // redirecting to /login would hide a misconfigured realm or an unreachable
  // Keycloak behind a login button that then fails the same way.
  if (auth.error) {
    return (
      <div className="grid min-h-dvh place-items-center p-6">
        <div className="max-w-sm space-y-3 text-center">
          <p className="font-medium text-destructive">Could not verify your session</p>
          <p className="text-sm text-muted-foreground">{auth.error.message}</p>
          <p className="text-xs text-muted-foreground">
            If this persists, check that the Keycloak container is running.
          </p>
          <Button variant="outline" onClick={() => void auth.signinRedirect()}>
            Try signing in again
          </Button>
        </div>
      </div>
    );
  }

  if (!auth.isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  const current = location.pathname + location.search;
  if (returnTo && returnTo !== current) {
    return <Navigate to={returnTo} replace />;
  }

  return <Outlet />;
}
