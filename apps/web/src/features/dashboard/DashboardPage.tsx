import { ChatPanel } from "@/features/chat/ChatPanel";
import { HistoryCard } from "./HistoryCard";
import { StatsCard } from "./StatsCard";

/**
 * Home screen — the Center + Right columns of the 3-column layout (the Left
 * Sidebar comes from AppLayout). Center: stats + recent history. Right: the chat
 * panel, the app's primary interaction.
 *
 * Below `lg` the two columns stack and the chat moves *first*: it is why an
 * employee opens the app, and burying it under two summary cards on a phone
 * would mean scrolling past them on every visit.
 *
 * The left track is `minmax(0,1fr)`, not `1fr`. A bare `1fr` floors the track at
 * its min-content width, and the history rows truncate their titles — the
 * `white-space: nowrap` that an ellipsis requires makes each row's min-content
 * the *full, untruncated* title, which measured ~570px for the column. Once the
 * content region was narrower than that floor plus the chat's 380px minimum, the
 * grid stopped shrinking and overflowed sideways instead.
 */
export function DashboardPage() {
  return (
    <div className="grid h-full grid-cols-1 gap-4 p-4 sm:gap-6 sm:p-6 lg:grid-cols-[minmax(0,1fr)_minmax(380px,44%)]">
      <div className="space-y-4 sm:space-y-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            Ask questions and review your recent conversations.
          </p>
        </div>
        <StatsCard />
        <HistoryCard />
      </div>

      {/* Chat needs a bounded height so its own body scrolls rather than the
          page. Stacked, that is a fixed slice — enough for an answer plus its
          sources without swallowing the screen. `order` puts it above the cards
          only while stacked.

          On `lg` the height is `auto` so the grid stretches it to the row. It
          used to be a hardcoded `calc(100dvh-3rem)`, which matched the row only
          while the left column stayed shorter than the viewport: the fifth
          history row pushed that column past it and the two card stacks ended at
          different heights. Stretching tracks the row whatever the row does. */}
      <div className="order-first h-[65dvh] min-h-[420px] lg:order-none lg:h-auto">
        <ChatPanel />
      </div>
    </div>
  );
}
