import type { User } from "oidc-client-ts";

import type { UserRole } from "@/types";

type RealmAccess = { realm_access?: { roles?: string[] } };

/**
 * Read the Keycloak realm roles from the *access* token.
 *
 * Realm roles live under `realm_access.roles` in the access token, not the ID
 * token (`user.profile`), so we decode the JWT payload ourselves. This mirrors
 * the backend exactly: `admin` is a composite role that also grants `employee`,
 * so we take the highest. See backend `core/security.py::_role_from_claims`.
 */
export function roleFromUser(user: User | null | undefined): UserRole | null {
  const roles = decodeRealmRoles(user?.access_token);
  if (!roles) return null;
  return roles.includes("admin") ? "admin" : "employee";
}

export function isAdmin(user: User | null | undefined): boolean {
  return roleFromUser(user) === "admin";
}

function decodeRealmRoles(accessToken: string | undefined): string[] | null {
  if (!accessToken) return null;
  try {
    const payload = accessToken.split(".")[1];
    // JWT uses base64url; make it plain base64 before decoding.
    const json = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
    const claims = JSON.parse(json) as RealmAccess;
    return claims.realm_access?.roles ?? [];
  } catch {
    return null;
  }
}
