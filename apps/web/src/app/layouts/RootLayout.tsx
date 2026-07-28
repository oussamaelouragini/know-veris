import { Outlet } from "react-router-dom";

import { SessionExpiredDialog } from "@/features/auth/SessionExpiredDialog";

/**
 * Outermost route element. It renders nothing of its own — it exists so that
 * the session-expired dialog sits *above* the auth gate: when the session dies,
 * <ProtectedRoute> immediately bounces to /login, and a dialog mounted inside it
 * would unmount in the same tick, leaving the user on a login screen with no
 * explanation of what just happened.
 */
export function RootLayout() {
  return (
    <>
      <Outlet />
      <SessionExpiredDialog />
    </>
  );
}
