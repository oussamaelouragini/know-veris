import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "react-oidc-context";

import { roleFromUser } from "./roles";
import type { UserRole } from "@/types";

/**
 * Authorization gate, nested inside <ProtectedRoute> (so the user is already
 * authenticated here). Renders the nested routes only if the user holds the
 * required realm role; otherwise redirects home.
 *
 * `admin` is composite and also grants `employee`, so an admin passes an
 * `employee` guard — the check is "does the user's role satisfy the requirement",
 * matching the backend's `require_admin`.
 */
export function RoleGuard({ role }: { role: UserRole }) {
  const auth = useAuth();
  const current = roleFromUser(auth.user);

  const allowed = role === "employee" ? current !== null : current === "admin";
  if (!allowed) return <Navigate to="/" replace />;

  return <Outlet />;
}
