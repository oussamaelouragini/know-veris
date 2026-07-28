import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "react-oidc-context";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

type FromState = { from?: { pathname?: string } };

/**
 * Public landing page. There is no local login form — identity is owned by
 * Keycloak, so the single action redirects into the OIDC + PKCE flow. Once
 * authenticated we send the user back to where they were headed (or home).
 */
export function LoginPage() {
  const auth = useAuth();
  const location = useLocation();
  const from = (location.state as FromState | null)?.from?.pathname ?? "/";

  if (auth.isAuthenticated) return <Navigate to={from} replace />;

  return (
    <main className="grid min-h-dvh place-items-center bg-muted/30 p-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="text-center">
          <CardTitle className="text-xl">KnowVeris AI</CardTitle>
          <CardDescription>
            Sign in with your Keycloak account to continue.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {auth.error && (
            <p className="text-center text-sm text-destructive">{auth.error.message}</p>
          )}
          <Button
            className="w-full"
            disabled={auth.isLoading}
            onClick={() => void auth.signinRedirect()}
          >
            {auth.isLoading ? "Loading…" : "Log in"}
          </Button>
        </CardContent>
      </Card>
    </main>
  );
}
