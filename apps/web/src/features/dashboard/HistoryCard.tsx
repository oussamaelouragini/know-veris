import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConversationList } from "@/features/conversations/ConversationList";

/** Recent conversations, with a link through to the full History page. */
export function HistoryCard() {
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle>Recent history</CardTitle>
        <Link
          to="/history"
          className="inline-flex items-center gap-1 text-sm font-medium text-muted-foreground hover:text-foreground"
        >
          View all <ArrowRight className="size-4" />
        </Link>
      </CardHeader>
      <CardContent>
        <ConversationList limit={5} />
      </CardContent>
    </Card>
  );
}
