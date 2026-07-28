import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import { CheckCircle2, TriangleAlert, X } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Minimal toast stack — no dependency, one provider, one `useToast()` hook.
 *
 * It exists for the failures that have nowhere to render: a delete that comes
 * back 500, a status poll that starts failing. Those run from a mutation
 * callback, after the row they belonged to is already gone from the screen, so
 * an inline error message has no anchor. Anything a form owns stays inline —
 * a toast is for what would otherwise fail silently.
 */

type ToastVariant = "error" | "success";
type Toast = { id: number; message: string; variant: ToastVariant };

type ToastApi = {
  /** Report a failure. Stays up long enough to read a sentence. */
  error: (message: string) => void;
  /** Confirm something that left no visible trace. */
  success: (message: string) => void;
};

const ToastContext = createContext<ToastApi | null>(null);

const DURATION: Record<ToastVariant, number> = { error: 7000, success: 3500 };

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(0);

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
  }, []);

  const push = useCallback(
    (message: string, variant: ToastVariant) => {
      const id = ++nextId.current;
      setToasts((prev) => [...prev, { id, message, variant }]);
      window.setTimeout(() => dismiss(id), DURATION[variant]);
    },
    [dismiss],
  );

  const api = useMemo<ToastApi>(
    () => ({
      error: (message) => push(message, "error"),
      success: (message) => push(message, "success"),
    }),
    [push],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        // `aria-live` so a screen reader announces the failure; pointer-events
        // are re-enabled per toast so the stack never blocks the UI behind it.
        role="status"
        aria-live="polite"
        className="pointer-events-none fixed inset-x-4 bottom-4 z-60 flex flex-col items-center gap-2 sm:inset-x-auto sm:right-4 sm:items-end"
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={cn(
              "pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-lg border p-3 text-sm shadow-lg",
              toast.variant === "error"
                ? "border-destructive/30 bg-destructive text-destructive-foreground"
                : "border-border bg-card text-card-foreground",
            )}
          >
            {toast.variant === "error" ? (
              <TriangleAlert className="mt-0.5 size-4 shrink-0" />
            ) : (
              <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-500" />
            )}
            <p className="min-w-0 flex-1 wrap-break-word">{toast.message}</p>
            <button
              type="button"
              aria-label="Dismiss"
              className="shrink-0 rounded opacity-70 transition-opacity hover:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              onClick={() => dismiss(toast.id)}
            >
              <X className="size-4" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const api = useContext(ToastContext);
  if (!api) throw new Error("useToast must be used inside <ToastProvider>");
  return api;
}
