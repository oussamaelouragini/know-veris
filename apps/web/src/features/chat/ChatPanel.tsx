import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { MessagesSquare, SendHorizontal, SquarePen, StopCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/state";
import { streamChat } from "./api";
import { ChatTurn, type Turn } from "./ChatTurn";

/**
 * Chat panel — the right column of the home screen.
 *
 * Streams the answer over SSE (see `api.ts`): tokens land in the current turn as
 * they arrive, and the closing `final` event brings the citations, the flags and
 * the timings. Turns after the first carry `conversation_id`, so a session is
 * one conversation server-side.
 *
 * Streaming is deliberately hand-rolled rather than run through a TanStack Query
 * mutation: the interesting state here is the partial answer, which arrives
 * dozens of times per second and belongs in component state, not in the cache.
 * The conversation list *is* cached, and is invalidated when a turn completes.
 */
export function ChatPanel() {
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const turnCounter = useRef(0);
  const scrollRef = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();

  // Follow the stream: keep the newest tokens in view.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [turns]);

  // Leaving the page mid-answer must not leave the request hanging.
  useEffect(() => () => abortRef.current?.abort(), []);

  const patch = useCallback((id: string, update: (turn: Turn) => Turn) => {
    setTurns((prev) => prev.map((turn) => (turn.id === id ? update(turn) : turn)));
  }, []);

  /**
   * `retryOf` re-asks a question whose turn already failed, and replaces that
   * turn instead of appending a second copy of the same question. On CPU an
   * answer costs 60-90 s, so a transient failure must not force the user to
   * retype anything.
   */
  async function ask(text?: string, retryOf?: string) {
    const asked = (text ?? question).trim();
    if (!asked || pending) return;

    const id = retryOf ?? `turn-${++turnCounter.current}`;
    const fresh: Turn = {
      id,
      question: asked,
      answer: "",
      status: "streaming",
      response: null,
      error: null,
    };
    setTurns((prev) =>
      retryOf ? prev.map((turn) => (turn.id === retryOf ? fresh : turn)) : [...prev, fresh],
    );
    if (!retryOf) setQuestion("");
    setPending(true);

    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const response = await streamChat({
        question: asked,
        conversationId,
        signal: controller.signal,
        onToken: (delta) => patch(id, (turn) => ({ ...turn, answer: turn.answer + delta })),
      });
      setConversationId(response.conversation_id);
      // Trust the persisted answer over the concatenated deltas — a refusal
      // never streams any token, and guardrail 2 may have stripped a citation.
      patch(id, (turn) => ({ ...turn, answer: response.answer, status: "done", response }));
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
    } catch (error) {
      const stopped = controller.signal.aborted;
      patch(id, (turn) => ({
        ...turn,
        status: stopped ? "stopped" : "error",
        error: stopped ? null : error instanceof Error ? error.message : String(error),
      }));
    } finally {
      abortRef.current = null;
      setPending(false);
    }
  }

  function newConversation() {
    abortRef.current?.abort();
    setTurns([]);
    setConversationId(null);
  }

  return (
    <Card className="flex h-full flex-col overflow-hidden">
      <div className="flex items-start justify-between gap-2 border-b border-border px-4 py-3">
        <div>
          <h2 className="font-semibold">Ask a question</h2>
          <p className="text-xs text-muted-foreground">
            Answers are grounded in the indexed documents only.
          </p>
        </div>
        {turns.length > 0 && (
          <Button variant="ghost" size="sm" onClick={newConversation} title="New conversation">
            <SquarePen />
            New
          </Button>
        )}
      </div>

      <div ref={scrollRef} className="flex-1 space-y-6 overflow-y-auto p-4">
        {turns.length === 0 ? (
          <EmptyState
            icon={MessagesSquare}
            title="Ask in French, English or Arabic."
            hint="The answer and the exact documents it came from appear here."
          />
        ) : (
          turns.map((turn) => (
            <ChatTurn
              key={turn.id}
              turn={turn}
              onRetry={pending ? undefined : () => void ask(turn.question, turn.id)}
            />
          ))
        )}
      </div>

      <div className="border-t border-border p-3">
        <textarea
          className="w-full resize-none rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          rows={3}
          placeholder="Ask a question about the indexed documents…"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void ask();
          }}
        />
        <div className="mt-2 flex items-center justify-between">
          <span className="text-xs text-muted-foreground">⌘/Ctrl + Enter</span>
          {pending ? (
            <Button variant="outline" size="sm" onClick={() => abortRef.current?.abort()}>
              <StopCircle />
              Stop
            </Button>
          ) : (
            <Button onClick={() => void ask()} disabled={!question.trim()} size="sm">
              <SendHorizontal />
              Ask
            </Button>
          )}
        </div>
      </div>
    </Card>
  );
}
