import { useState } from "react";
import { UserPlus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import type { AdminUserCreate, AdminUserCreated } from "@/types";
import { adminErrorMessage, useCreateUser } from "./api";

const EMPTY: AdminUserCreate = { username: "", email: "", first_name: "", last_name: "" };

/**
 * Employee-account creation. The account is provisioned in Keycloak (username,
 * email, `employee` role, temporary password) and mirrored into Postgres by the
 * backend — this form only collects the four fields and hands the returned
 * one-time password to the page.
 */
export function CreateUserForm({ onCreated }: { onCreated: (user: AdminUserCreated) => void }) {
  const [form, setForm] = useState<AdminUserCreate>(EMPTY);
  const create = useCreateUser();

  const complete = Object.values(form).every((value) => value.trim().length > 0);

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!complete) return;
    create.mutate(form, {
      onSuccess: (user) => {
        setForm(EMPTY);
        onCreated(user);
      },
    });
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Username" htmlFor="username">
          <Input
            id="username"
            value={form.username}
            autoComplete="off"
            onChange={(e) => setForm({ ...form, username: e.target.value })}
          />
        </Field>
        <Field label="Email" htmlFor="email">
          <Input
            id="email"
            type="email"
            value={form.email}
            autoComplete="off"
            onChange={(e) => setForm({ ...form, email: e.target.value })}
          />
        </Field>
        <Field label="First name" htmlFor="first_name">
          <Input
            id="first_name"
            value={form.first_name}
            onChange={(e) => setForm({ ...form, first_name: e.target.value })}
          />
        </Field>
        <Field label="Last name" htmlFor="last_name">
          <Input
            id="last_name"
            value={form.last_name}
            onChange={(e) => setForm({ ...form, last_name: e.target.value })}
          />
        </Field>
      </div>

      {create.error && (
        <p className="rounded-md bg-destructive/10 p-2 text-sm text-destructive">
          {adminErrorMessage(create.error)}
        </p>
      )}

      <Button type="submit" size="sm" disabled={!complete || create.isPending}>
        <UserPlus />
        {create.isPending ? "Creating…" : "Create employee"}
      </Button>
    </form>
  );
}
