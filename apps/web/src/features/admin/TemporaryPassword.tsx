import { useState } from "react";
import { Check, Copy, KeyRound } from "lucide-react";

import { Button } from "@/components/ui/button";

/**
 * The one-time temporary password panel.
 *
 * Keycloak stores the password hashed and `temporary: true` forces a change at
 * first login, so this value is unrecoverable the moment the panel is dismissed
 * — hence the explicit warning and the copy button. It is deliberately not
 * cached in TanStack Query: a secret should not sit in a cache keyed by user.
 */
export function TemporaryPassword({
  username,
  password,
  onDismiss,
}: {
  username: string;
  password: string;
  onDismiss: () => void;
}) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(password);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false); // clipboard blocked — the value is on screen anyway
    }
  }

  return (
    <div className="space-y-3 rounded-lg border border-amber-300 bg-amber-50 p-4 text-amber-900">
      <div className="flex items-center gap-2 text-sm font-semibold">
        <KeyRound className="size-4" />
        Temporary password for {username}
      </div>
      <div className="flex items-center gap-2">
        <code className="flex-1 truncate rounded-md bg-white/70 px-3 py-2 font-mono text-sm">
          {password}
        </code>
        <Button variant="outline" size="sm" onClick={copy}>
          {copied ? <Check /> : <Copy />}
          {copied ? "Copied" : "Copy"}
        </Button>
      </div>
      <p className="text-xs">
        Shown once — it cannot be retrieved later. Give it to the employee; they must change it
        at first login. If it is lost, reset the password instead.
      </p>
      <Button variant="secondary" size="sm" onClick={onDismiss}>
        I have copied it
      </Button>
    </div>
  );
}
