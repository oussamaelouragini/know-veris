import { MessagesSquare } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useConversations } from "@/features/conversations/api";

/**
 * Total conversations for the signed-in user.
 *
 * It shares the `["conversations"]` query with the list below it, so a failure
 * here is always accompanied by the list's own error — which is the one that
 * carries the message and the retry button. Repeating both would put two error
 * boxes on the same card stack, so this one stays a single quiet line.
 */
export function StatsCard() {
  const { data, isLoading, isError } = useConversations();
  const count = data?.length ?? 0;
  const messages = data?.reduce((sum, c) => sum + c.message_count, 0) ?? 0;

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          Your conversations
        </CardTitle>
        <MessagesSquare className="size-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-9 w-16" />
        ) : isError ? (
          <p className="text-sm text-destructive">Failed to load.</p>
        ) : (
          <>
            <div className="text-3xl font-bold">{count}</div>
            <p className="text-xs text-muted-foreground">
              {messages} message{messages === 1 ? "" : "s"} total
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
