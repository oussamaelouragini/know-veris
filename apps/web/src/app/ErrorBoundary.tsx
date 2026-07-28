import { Component } from "react";
import { isRouteErrorResponse, useRouteError } from "react-router-dom";
import { RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * The screen a user sees instead of a blank page.
 *
 * There are two ways this app can die and they need different catchers, so both
 * live here: React only surfaces a render/lifecycle crash to a class component
 * (<AppErrorBoundary>), while React Router intercepts anything thrown from a
 * route before it reaches that boundary and expects an `errorElement`
 * (<RouteErrorElement>). Wiring only one of them still leaves a white screen
 * for half the failures.
 */

function Fallback({ title, detail }: { title: string; detail?: string }) {
  return (
    <main className="grid min-h-dvh place-items-center bg-muted/30 p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>{title}</CardTitle>
          <CardDescription>
            The screen failed to render. Reloading usually clears it — your
            conversations and documents are stored server-side and are not affected.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {detail && (
            // Kept visible rather than console-only: during the internship the
            // person hitting this is the one who has to diagnose it.
            <pre className="max-h-40 overflow-auto rounded-md bg-muted p-3 text-xs text-muted-foreground">
              {detail}
            </pre>
          )}
          <div className="flex gap-2">
            <Button onClick={() => window.location.assign("/")}>
              <RefreshCw />
              Reload the app
            </Button>
          </div>
        </CardContent>
      </Card>
    </main>
  );
}

/** Route-level errors (thrown from a loader, an action, or a route render). */
export function RouteErrorElement() {
  const error = useRouteError();
  if (isRouteErrorResponse(error)) {
    return <Fallback title={`${error.status} ${error.statusText}`} detail={String(error.data ?? "")} />;
  }
  return (
    <Fallback
      title="Something broke on this page"
      detail={error instanceof Error ? `${error.message}\n\n${error.stack ?? ""}`.trim() : undefined}
    />
  );
}

type State = { error: Error | null };

/**
 * Outermost net, above the router — catches a crash in the providers or in the
 * router itself, which no `errorElement` can see.
 */
export class AppErrorBoundary extends Component<{ children: React.ReactNode }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: { componentStack?: string | null }) {
    // No error-reporting service by design (nothing leaves the machine), so the
    // console is the only place the stack survives for a bug report.
    console.error("Unhandled render error", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <Fallback
          title="The application stopped"
          detail={`${this.state.error.message}\n\n${this.state.error.stack ?? ""}`.trim()}
        />
      );
    }
    return this.props.children;
  }
}
