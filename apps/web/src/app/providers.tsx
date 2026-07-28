import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "react-oidc-context";

import { ToastProvider } from "@/components/ui/toast";
import { onSigninCallback, userManager } from "@/lib/oidc";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // RAG answers are expensive on CPU — don't refetch on window focus, and
      // keep results around. Per-query overrides tune this where it matters.
      refetchOnWindowFocus: false,
      // Retrying a 401/403 is pointless — the session or the role is the
      // problem, and each retry produces another expiry signal. Anything else
      // (a container still warming up, a dropped request) gets one retry.
      retry: (failureCount, error) => {
        const status = (error as { response?: { status?: number } }).response?.status;
        if (status === 401 || status === 403 || status === 404) return false;
        return failureCount < 1;
      },
      staleTime: 30_000,
    },
    mutations: {
      // A mutation is a user-initiated write: replaying it silently could
      // create a second employee account. Surface the failure instead.
      retry: false,
    },
  },
});

/**
 * App-wide providers: the shared OIDC session (react-oidc-context, driven by our
 * single UserManager) wrapping TanStack Query, wrapping the toast stack. Auth is
 * outermost so the Axios interceptor — and therefore every query — always sees
 * the current token; toasts are innermost so any feature can report a failure
 * that has nowhere else to render.
 */
export function AppProviders({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider userManager={userManager} onSigninCallback={onSigninCallback}>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>{children}</ToastProvider>
      </QueryClientProvider>
    </AuthProvider>
  );
}
