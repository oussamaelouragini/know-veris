import { useState } from "react";
import { MessageSquare, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/state";
import { useToast } from "@/components/ui/toast";
import { friendlyErrorMessage } from "@/lib/apiClient";
import { timeAgo } from "@/lib/format";
import type { Conversation } from "@/types";
import { useConversations, useDeleteConversation } from "./api";

/**
 * The user's conversations as a list. `limit` trims it for the dashboard
 * HistoryCard; the History page passes none to show everything. Each row can be
 * deleted (with a confirmation prompt); selecting a row to reopen it in the chat
 * panel lands with multi-turn history (D5).
 */
export function ConversationList({ limit }: { limit?: number }) {
  const { data, isLoading, isError, error, refetch, isFetching } = useConversations();
  const remove = useDeleteConversation();
  const [pending, setPending] = useState<Conversation | null>(null);
  const toast = useToast();

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: limit ?? 4 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <ErrorState
        title="Could not load your conversations."
        message={friendlyErrorMessage(error)}
        onRetry={() => void refetch()}
        retrying={isFetching}
      />
    );
  }

  const items = limit ? data!.slice(0, limit) : data!;

  if (items.length === 0) {
    return (
      <EmptyState
        icon={MessageSquare}
        title="No conversations yet."
        hint="Ask your first question in the chat panel."
      />
    );
  }

  function confirmDelete() {
    if (!pending) return;
    const { id, title } = pending;
    remove.mutate(id, {
      // The row is gone as soon as the dialog closes, so an inline message has
      // nowhere to attach — without the toast a failed delete looks like a
      // successful one until the list refetches.
      onError: (cause) =>
        toast.error(`Could not delete “${title ?? "Untitled"}”: ${friendlyErrorMessage(cause)}`),
      onSettled: () => setPending(null),
    });
  }

  return (
    <>
      <ul className="divide-y divide-border">
        {items.map((c) => (
          <li key={c.id} className="group flex items-center gap-3 py-3">
            <MessageSquare className="size-4 shrink-0 text-muted-foreground" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{c.title ?? "Untitled"}</p>
              <p className="text-xs text-muted-foreground">
                {c.message_count} message{c.message_count === 1 ? "" : "s"}
              </p>
            </div>
            <span className="shrink-0 text-xs text-muted-foreground">
              {timeAgo(c.updated_at)}
            </span>
            <Button
              variant="ghost"
              size="icon"
              className="size-8 shrink-0 text-muted-foreground opacity-60 hover:text-destructive group-hover:opacity-100"
              aria-label="Delete conversation"
              onClick={() => setPending(c)}
            >
              <Trash2 className="size-4" />
            </Button>
          </li>
        ))}
      </ul>

      <ConfirmDialog
        open={pending !== null}
        title="Delete this conversation?"
        description={
          pending
            ? `“${pending.title ?? "Untitled"}” and its messages will be permanently removed. This cannot be undone.`
            : undefined
        }
        busy={remove.isPending}
        onConfirm={confirmDelete}
        onCancel={() => setPending(null)}
      />
    </>
  );
}
