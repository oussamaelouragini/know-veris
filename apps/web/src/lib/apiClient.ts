import axios from "axios";

import { userManager } from "./oidc";
import { notifySessionExpired } from "./session";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

/** Base URL of the versioned API — shared by the Axios instance and `authorizedFetch`. */
export const API_BASE_URL = `${API_URL}/api/v1`;

/**
 * The single Axios instance for the whole app. Every call to the API goes
 * through here so the JWT is attached in exactly one place (project rule:
 * "never pass a token by hand").
 */
export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: { "Content-Type": "application/json" },
});

/**
 * The error text FastAPI put in `detail`.
 *
 * `detail` is a string for an explicit HTTPException, but a list of
 * `{loc, msg, type}` objects for a 422 validation error — interpolating the raw
 * value straight into a message yields "[object Object]", so unwrap it here once
 * for every feature.
 */
export function apiErrorDetail(error: unknown): string | null {
  if (!axios.isAxiosError(error)) return null;
  const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => (item as { msg?: unknown }).msg)
      .filter((msg): msg is string => typeof msg === "string");
    if (messages.length) return messages.join("; ");
  }
  return null;
}

/** Status codes that mean the same thing everywhere, so they are worded once. */
const STATUS_MESSAGE: Record<number, string> = {
  403: "You do not have permission to do that.",
  404: "That item no longer exists.",
  429: "Too many requests — wait a moment and try again.",
  500: "The server hit an unexpected error.",
  502: "A service the API depends on is unreachable.",
  503: "The service is temporarily unavailable.",
  504: "The server took too long to answer.",
};

/**
 * One sentence an employee can act on, for any failure the API can produce.
 *
 * Order matters: the endpoint's own `detail` is the most specific thing we have
 * and wins, then the generic status wording, and only then the raw exception —
 * which is what the user would otherwise see for a network drop ("Network
 * Error"), the single most common failure on a laptop running everything
 * locally.
 */
export function friendlyErrorMessage(error: unknown, fallback = "Something went wrong."): string {
  if (axios.isAxiosError(error)) {
    if (!error.response) {
      return error.code === "ECONNABORTED"
        ? "The request timed out."
        : "Cannot reach the server. Check that the API container is running.";
    }
    const detail = apiErrorDetail(error);
    if (detail) return detail;
    const known = STATUS_MESSAGE[error.response.status];
    if (known) return known;
    return `Request failed (${error.response.status}).`;
  }
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

/**
 * `fetch` against the API, under the same auth rules as the Axios instance.
 *
 * Axios buffers a response before resolving, so it cannot read an SSE body while
 * it streams — the chat stream goes through `fetch` instead. The token still
 * comes from exactly one place (the shared UserManager), and a 401 is handled
 * exactly as the Axios interceptor handles it, so the session-expired dialog
 * behaves the same whichever transport hit the wall first.
 */
export async function authorizedFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const user = await userManager.getUser();
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  if (user?.access_token) headers.set("Authorization", `Bearer ${user.access_token}`);

  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
  if (response.status === 401) await endSession();
  return response;
}

/**
 * Request interceptor — inject the Bearer token.
 *
 * The token is read from the shared UserManager (lib/oidc.ts), the same session
 * `react-oidc-context` drives, so it is always the current one. `automaticSilentRenew`
 * keeps it fresh; if it is nonetheless expired we still send it and let the
 * response interceptor handle the 401 rather than block the request here.
 */
apiClient.interceptors.request.use(async (config) => {
  const user = await userManager.getUser();
  if (user?.access_token) {
    config.headers.Authorization = `Bearer ${user.access_token}`;
  }
  return config;
});

/**
 * A 401 means the token is stale or Keycloak ended the session.
 *
 * Dropping the local user is not enough on its own: <ProtectedRoute> would then
 * silently bounce to /login and the user loses both the page they were on and
 * any idea of why. So we also announce it, and <SessionExpiredDialog> explains
 * it and offers the one-click way back in.
 */
async function endSession(): Promise<void> {
  await userManager.removeUser();
  notifySessionExpired("unauthorized");
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (axios.isAxiosError(error) && error.response?.status === 401) {
      await endSession();
    }
    return Promise.reject(error);
  },
);
