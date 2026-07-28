import { useState } from "react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { CreateUserForm } from "./CreateUserForm";
import { TemporaryPassword } from "./TemporaryPassword";
import { UsersTable } from "./UsersTable";

type Secret = { username: string; password: string };

/**
 * Employee-account management (PLAN §3). Identity is owned by Keycloak: this
 * screen creates, disables and resets accounts through the API's service
 * account, and surfaces the temporary password exactly once.
 */
export function AdminUsersPage() {
  const [secret, setSecret] = useState<Secret | null>(null);

  return (
    <div className="mx-auto max-w-5xl space-y-4 p-4 sm:space-y-6 sm:p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Employees</h1>
        <p className="text-sm text-muted-foreground">
          Accounts live in Keycloak. Registration is disabled — an admin creates them here.
        </p>
      </div>

      {secret && (
        <TemporaryPassword
          username={secret.username}
          password={secret.password}
          onDismiss={() => setSecret(null)}
        />
      )}

      <Card>
        <CardHeader>
          <CardTitle>New employee</CardTitle>
          <CardDescription>
            The account gets the <code>employee</code> role and a temporary password to change at
            first login.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <CreateUserForm
            onCreated={(user) =>
              setSecret({ username: user.username, password: user.temporary_password })
            }
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Accounts</CardTitle>
          <CardDescription>Disable an account instead of deleting it.</CardDescription>
        </CardHeader>
        <CardContent>
          <UsersTable
            onPasswordReset={(username, password) => setSecret({ username, password })}
          />
        </CardContent>
      </Card>
    </div>
  );
}
