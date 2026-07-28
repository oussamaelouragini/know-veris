import { Loader2, RotateCcw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { directionOf } from "@/lib/rtl";
import { cn } from "@/lib/utils";
import type { ChatResponse } from "@/types";
import { SourceCard } from "./SourceCard";

/** One question and the answer being (or already) streamed back for it. */
export type Turn = {
  /** Client-side id — the server one only arrives with the `final` event. */
  id: string;
  question: string;
  /** Grows token by token while streaming. */
  answer: string;
  status: "streaming" | "done" | "stopped" | "error";
  response: ChatResponse | null;
  error: string | null;
};

export function ChatTurn({ turn, onRetry }: { turn: Turn; onRetry?: () => void }) {
  const questionDir = directionOf(turn.question);
  // While streaming we only have partial text, so the direction is sniffed from
  // the script; the `final` event replaces it with the pipeline's detection.
  const answerDir = directionOf(turn.answer, turn.response?.language);
  const streaming = turn.status === "streaming";
  const citations = turn.response?.citations ?? [];

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <p
          dir={questionDir}
          className={cn(
            "max-w-[85%] whitespace-pre-wrap rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground",
            questionDir === "rtl" && "text-right",
          )}
        >
          {turn.question}
        </p>
      </div>

      <div className="space-y-3">
        {streaming && !turn.answer && (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            Retrieving sources and generating… the first tokens take a few seconds on CPU.
          </p>
        )}

        {turn.answer && (
          <p
            dir={answerDir}
            className={cn(
              "whitespace-pre-wrap text-sm leading-relaxed",
              answerDir === "rtl" && "text-right",
            )}
          >
            {turn.answer}
            {streaming && <span className="ml-0.5 animate-pulse">▍</span>}
          </p>
        )}

        {turn.status === "stopped" && (
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-xs text-muted-foreground">
              Stopped — this answer was not saved with its sources.
            </p>
            {onRetry && (
              <Button variant="ghost" size="sm" onClick={onRetry}>
                <RotateCcw />
                Ask again
              </Button>
            )}
          </div>
        )}

        {turn.status === "error" && (
          <div className="space-y-2 rounded-md border border-destructive/30 bg-destructive/10 p-3">
            <p className="text-sm text-destructive">{turn.error}</p>
            {/* A retry that reuses the question matters more here than anywhere
                else: the alternative is retyping it and waiting another
                60-90 s from scratch. */}
            {onRetry && (
              <Button variant="outline" size="sm" onClick={onRetry}>
                <RotateCcw />
                Try again
              </Button>
            )}
          </div>
        )}

        {turn.response && (
          <>
            <div className="flex flex-wrap gap-2">
              {turn.response.refused && (
                <Badge variant="warning">No answer in the indexed documents</Badge>
              )}
              {turn.response.unverified && (
                <Badge variant="warning">Unverified — no citation</Badge>
              )}
            </div>

            {citations.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Sources
                </p>
                {citations.map((citation) => (
                  <SourceCard key={citation.marker} citation={citation} />
                ))}
              </div>
            )}

            <p className="text-xs text-muted-foreground">
              {turn.response.model_used ?? "no model"}
              {turn.response.latency_ms != null &&
                ` · ${(turn.response.latency_ms / 1000).toFixed(1)} s`}
              {turn.response.language && ` · ${turn.response.language}`}
            </p>
          </>
        )}
      </div>
    </div>
  );
}
