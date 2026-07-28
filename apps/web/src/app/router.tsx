import { createBrowserRouter } from "react-router-dom";

import { RouteErrorElement } from "./ErrorBoundary";
import { AppLayout } from "./layouts/AppLayout";
import { RootLayout } from "./layouts/RootLayout";
import { LoginPage } from "@/features/auth/LoginPage";
import { ProtectedRoute } from "@/features/auth/ProtectedRoute";
import { RoleGuard } from "@/features/auth/RoleGuard";
import { AdminUsersPage } from "@/features/admin/AdminUsersPage";
import { HistoryPage } from "@/features/conversations/HistoryPage";
import { DashboardPage } from "@/features/dashboard/DashboardPage";
import { DocumentsPage } from "@/features/documents/DocumentsPage";
import { NotFoundPage } from "@/features/common/NotFoundPage";

/**
 * Route map. The home screen (Dashboard) hosts the chat panel, so there is no
 * separate /chat route. Admin routes are wrapped in <RoleGuard role="admin">.
 *   /login                        public
 *   / , /history                  authenticated
 *   /admin/documents, /admin/users  admin only
 *
 * Everything hangs off <RootLayout> so the session-expired dialog is mounted on
 * every route — including /login, which is exactly where the user gets bounced
 * when the session dies — and so one `errorElement` covers the whole tree.
 */
export const router = createBrowserRouter([
  {
    element: <RootLayout />,
    errorElement: <RouteErrorElement />,
    children: [
      { path: "/login", element: <LoginPage /> },
      {
        element: <ProtectedRoute />,
        children: [
          {
            element: <AppLayout />,
            children: [
              { index: true, element: <DashboardPage /> },
              { path: "history", element: <HistoryPage /> },
              {
                path: "admin",
                element: <RoleGuard role="admin" />,
                children: [
                  { path: "documents", element: <DocumentsPage /> },
                  { path: "users", element: <AdminUsersPage /> },
                ],
              },
            ],
          },
        ],
      },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);
