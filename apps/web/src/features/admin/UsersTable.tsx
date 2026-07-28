import { KeyRound, Power, Users } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/state";
import { useToast } from "@/components/ui/toast";
import type { AdminUser } from "@/types";
import { adminErrorMessage, useAdminUsers, useResetPassword, useSetUserEnabled } from "./api";

/**
 * Employee accounts, straight from Keycloak. There is no delete action by
 * design: an account is disabled, never removed, so past conversations and
 * audit entries keep pointing at a real user (PLAN §3).
 */
export function UsersTable({
  onPasswordReset,
}: {
  onPasswordReset: (username: string, password: string) => void;
}) {
  const { data, isLoading, isError, error, refetch, isFetching } = useAdminUsers();
  const setEnabled = useSetUserEnabled();
  const reset = useResetPassword();
  const toast = useToast();

  if (isLoading) {
    return (
      <div className="space-y-2">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }
  if (isError) {
    return (
      <ErrorState
        title="Could not load the accounts."
        message={adminErrorMessage(error)}
        onRetry={() => void refetch()}
        retrying={isFetching}
      />
    );
  }
  if (!data?.length) {
    return <EmptyState icon={Users} title="No employee account yet." hint="Create one above." />;
  }

  return (
    <div className="space-y-3">
      {(setEnabled.error || reset.error) && (
        <ErrorState
          title="The last action failed."
          message={adminErrorMessage(setEnabled.error ?? reset.error)}
        />
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-muted-foreground">
              <th className="py-2 pr-4 font-medium">Username</th>
              {/* Name and email fold into the username cell below `md` — three
                  identity columns plus two action buttons does not fit a phone. */}
              <th className="hidden py-2 pr-4 font-medium md:table-cell">Name</th>
              <th className="hidden py-2 pr-4 font-medium md:table-cell">Email</th>
              <th className="py-2 pr-4 font-medium">Status</th>
              <th className="py-2 font-medium sr-only">Actions</th>
            </tr>
          </thead>
          <tbody>
            {data.map((user) => (
              <UserRow
                key={user.id}
                user={user}
                // `variables` is the argument of the mutation currently in
                // flight, so one shared hook still reports per-row progress —
                // only the row being acted on spins.
                resetting={reset.isPending && reset.variables === user.id}
                toggling={setEnabled.isPending && setEnabled.variables?.id === user.id}
                anyResetPending={reset.isPending}
                anyTogglePending={setEnabled.isPending}
                onReset={() =>
                  reset.mutate(user.id, {
                    onSuccess: (data) => onPasswordReset(user.username, data.temporary_password),
                  })
                }
                onToggle={() =>
                  setEnabled.mutate(
                    { id: user.id, enabled: !user.enabled },
                    {
                      onSuccess: () =>
                        toast.success(`${user.username} ${user.enabled ? "disabled" : "enabled"}.`),
                    },
                  )
                }
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function fullName(user: AdminUser): string {
  return [user.first_name, user.last_name].filter(Boolean).join(" ") || "—";
}

function UserRow({
  user,
  resetting,
  toggling,
  anyResetPending,
  anyTogglePending,
  onReset,
  onToggle,
}: {
  user: AdminUser;
  resetting: boolean;
  toggling: boolean;
  anyResetPending: boolean;
  anyTogglePending: boolean;
  onReset: () => void;
  onToggle: () => void;
}) {
  return (
    <tr className="border-b border-border last:border-0">
      <td className="py-2 pr-4">
        <p className="font-medium">{user.username}</p>
        <p className="text-xs text-muted-foreground md:hidden">
          {[fullName(user), user.email].filter((value) => value && value !== "—").join(" · ")}
        </p>
      </td>
      <td className="hidden py-2 pr-4 text-muted-foreground md:table-cell">{fullName(user)}</td>
      <td className="hidden py-2 pr-4 text-muted-foreground md:table-cell">{user.email ?? "—"}</td>
      <td className="py-2 pr-4">
        <Badge variant={user.enabled ? "default" : "warning"}>
          {user.enabled ? "enabled" : "disabled"}
        </Badge>
      </td>
      <td className="py-2">
        <div className="flex flex-col justify-end gap-2 sm:flex-row">
          <Button
            variant="outline"
            size="sm"
            loading={resetting}
            disabled={anyResetPending}
            onClick={onReset}
          >
            {!resetting && <KeyRound />}
            Reset password
          </Button>
          <Button
            variant={user.enabled ? "outline" : "default"}
            size="sm"
            loading={toggling}
            disabled={anyTogglePending}
            onClick={onToggle}
          >
            {!toggling && <Power />}
            {user.enabled ? "Disable" : "Enable"}
          </Button>
        </div>
      </td>
    </tr>
  );
}
