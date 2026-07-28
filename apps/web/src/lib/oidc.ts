import { UserManager, WebStorageStateStore } from "oidc-client-ts";
import type { UserManagerSettings } from "oidc-client-ts";

import { notifySessionExpired } from "./session";

const KEYCLOAK_URL = import.meta.env.VITE_KEYCLOAK_URL ?? "http://localhost:8080";
const REALM = import.meta.env.VITE_KEYCLOAK_REALM ?? "knowveris";
const CLIENT_ID = import.meta.env.VITE_KEYCLOAK_CLIENT_ID ?? "knowveris-web";

/**
 * OIDC settings for the `knowveris-web` public client (authorization code + PKCE
 * S256 — matches infra/keycloak/realm-export.json). The access token carries the
 * `knowveris-api` audience via the client's audience mapper, so FastAPI accepts
 * it directly.
 */
const settings: UserManagerSettings = {
  authority: `${KEYCLOAK_URL}/realms/${REALM}`,
  client_id: CLIENT_ID,
  redirect_uri: window.location.origin + "/",
  post_logout_redirect_uri: window.location.origin + "/",
  response_type: "code",
  scope: "openid profile email",
  // Persist the session across reloads instead of the default in-memory store.
  userStore: new WebStorageStateStore({ store: window.localStorage }),
  // Refresh the access token in the background before it expires, so the Axios
  // interceptor always attaches a valid Bearer token.
  automaticSilentRenew: true,
};

/**
 * Single shared UserManager. It is the one source of truth for the session:
 * `react-oidc-context`'s <AuthProvider> drives the React tree from it, and the
 * Axios interceptor (lib/apiClient.ts) reads the current token from the same
 * instance — so no token is ever passed by hand.
 */
export const userManager = new UserManager(settings);

/**
 * Session expiry, detected proactively rather than on the next failed request.
 *
 * The realm gives an access token 5 minutes and idles the SSO session out after
 * 30 (PLAN §3), so a user who reads a long answer and then walks away comes
 * back to a dead session. Waiting for the next 401 means their next click is
 * silently swallowed; these events let the dialog appear the moment renewal
 * actually fails.
 *
 * `removeUser` here, not just a notification: it clears the stale token from
 * localStorage so nothing retries with it, and flips `isAuthenticated` so the
 * app stops issuing queries behind the dialog.
 */
userManager.events.addSilentRenewError((error) => {
  console.warn("Silent token renewal failed", error);
  void userManager.removeUser().then(() => notifySessionExpired("renew-failed"));
});

userManager.events.addAccessTokenExpired(() => {
  void userManager.removeUser().then(() => notifySessionExpired("expired"));
});

userManager.events.addUserSignedOut(() => {
  void userManager.removeUser().then(() => notifySessionExpired("signed-out"));
});

/** Strip the `?code=...&state=...` from the URL once the redirect completes. */
export function onSigninCallback(): void {
  window.history.replaceState({}, document.title, window.location.pathname);
}
