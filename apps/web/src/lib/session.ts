/**
 * Session-expiry signalling, kept out of React on purpose.
 *
 * Expiry is discovered in two places that are not components — the Axios/fetch
 * layer (a 401 came back) and the OIDC UserManager (silent renew failed, or the
 * SSO session ended in Keycloak). Both publish on this bus; a single dialog
 * inside the tree subscribes. That keeps `lib/` free of React imports and means
 * there is exactly one place that decides what the user sees.
 */

const EXPIRED_EVENT = "knowveris:session-expired";

/** Why the session ended — the dialog words itself differently for each. */
export type ExpiryReason = "expired" | "signed-out" | "renew-failed" | "unauthorized";

/** Announce that the session is no longer usable. Safe to call repeatedly. */
export function notifySessionExpired(reason: ExpiryReason): void {
  window.dispatchEvent(new CustomEvent<ExpiryReason>(EXPIRED_EVENT, { detail: reason }));
}

/** Subscribe to expiry. Returns the unsubscribe function, for a React effect. */
export function onSessionExpired(handler: (reason: ExpiryReason) => void): () => void {
  const listener = (event: Event) => handler((event as CustomEvent<ExpiryReason>).detail);
  window.addEventListener(EXPIRED_EVENT, listener);
  return () => window.removeEventListener(EXPIRED_EVENT, listener);
}

const RETURN_TO_KEY = "knowveris:return-to";

/**
 * Remember where the user was before we send them back to Keycloak.
 *
 * The OIDC `redirect_uri` is fixed to the app root (it has to match the client
 * registration), so without this an admin whose session expires on
 * /admin/users lands back on the dashboard. sessionStorage, not localStorage:
 * this is per-tab and must not outlive the browser session.
 */
export function rememberReturnTo(path: string): void {
  try {
    if (path && path !== "/") sessionStorage.setItem(RETURN_TO_KEY, path);
  } catch {
    /* storage blocked — losing the return path is not worth failing the login */
  }
}

/** Read and clear the remembered path. Returns null when there is nothing to restore. */
export function takeReturnTo(): string | null {
  try {
    const path = sessionStorage.getItem(RETURN_TO_KEY);
    if (path) sessionStorage.removeItem(RETURN_TO_KEY);
    return path;
  } catch {
    return null;
  }
}
