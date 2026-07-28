import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import axios from "axios";

import { apiClient, apiErrorDetail } from "@/lib/apiClient";
import type { AdminUser, AdminUserCreate, AdminUserCreated, PasswordReset } from "@/types";

/**
 * Employee-account management. Every call here is proxied by FastAPI to the
 * Keycloak Admin REST API through a service account (ADR-006) — the SPA never
 * talks to Keycloak's admin API itself, and no password is ever stored by us.
 */

const usersKey = ["admin", "users"] as const;

async function fetchUsers(): Promise<AdminUser[]> {
  const { data } = await apiClient.get<AdminUser[]>("/admin/users");
  return data;
}

export function useAdminUsers() {
  return useQuery({ queryKey: usersKey, queryFn: fetchUsers });
}

/** Create an employee. The temporary password comes back once and only once. */
export function useCreateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: AdminUserCreate): Promise<AdminUserCreated> => {
      const { data } = await apiClient.post<AdminUserCreated>("/admin/users", payload);
      return data;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: usersKey }),
  });
}

/** Enable or disable an account — we never delete one (traceability, PLAN §3). */
export function useSetUserEnabled() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, enabled }: { id: string; enabled: boolean }) => {
      await apiClient.patch(`/admin/users/${id}`, { enabled });
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: usersKey }),
  });
}

/** Reset a password; the new temporary one is shown once, like on creation. */
export function useResetPassword() {
  return useMutation({
    mutationFn: async (id: string): Promise<PasswordReset> => {
      const { data } = await apiClient.post<PasswordReset>(`/admin/users/${id}/reset-password`);
      return data;
    },
  });
}

/** Turn an API failure into something an admin can act on. */
export function adminErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = apiErrorDetail(error);
    if (error.response?.status === 409) return detail ?? "That username or email already exists.";
    if (error.response?.status === 502) return detail ?? "Keycloak is unreachable.";
    if (detail) return detail;
  }
  return error instanceof Error ? error.message : String(error);
}
