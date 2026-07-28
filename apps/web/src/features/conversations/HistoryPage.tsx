import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConversationList } from "./ConversationList";

/** Full conversation history (reached from the dashboard HistoryCard). */
export function HistoryPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-4 p-4 sm:space-y-6 sm:p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">History</h1>
        <p className="text-sm text-muted-foreground">All your conversations.</p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Conversations</CardTitle>
        </CardHeader>
        <CardContent>
          <ConversationList />
        </CardContent>
      </Card>
    </div>
  );
}
