import { authorizedFetch } from "@/lib/apiClient";
import type { ChatResponse } from "@/types";

/**
 * Chat transport — Server-Sent Events.
 *
 * `POST /api/v1/chat/stream` emits `token` events (one `{delta}` per generated
 * token) and closes with a single `final` event carrying the full ChatResponse:
 * citations, refusal/unverified flags, model, latency. On CPU the answer takes
 * 60-90 s, so streaming is what makes the wait legible — the first token lands
 * in seconds instead of a blank minute.
 *
 * The JWT is injected by `authorizedFetch`, never passed by hand.
 */

type ChatStreamOptions = {
  question: string;
  conversationId?: string | null;
  /** Called for every token delta, in order. */
  onToken: (delta: string) => void;
  signal?: AbortSignal;
};

/** One parsed SSE frame (`event:` + `data:` lines, terminated by a blank line). */
type Frame = { event: string; data: string };

function parseFrame(raw: string): Frame | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  return dataLines.length ? { event, data: dataLines.join("\n") } : null;
}

/** Best-effort error message from a non-2xx response (FastAPI sends `{detail}`). */
async function errorFrom(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
  } catch {
    /* not JSON — fall through to the status line */
  }
  return `Request failed (${response.status})`;
}

export async function streamChat({
  question,
  conversationId,
  onToken,
  signal,
}: ChatStreamOptions): Promise<ChatResponse> {
  let response: Response;
  try {
    response = await authorizedFetch("/chat/stream", {
      method: "POST",
      body: JSON.stringify({ question, conversation_id: conversationId ?? null }),
      signal,
    });
  } catch (error) {
    // An aborted fetch must stay an AbortError so the caller can tell "the user
    // pressed Stop" from "the API is down" — only the latter gets reworded.
    if (signal?.aborted) throw error;
    throw new Error("Cannot reach the server. Check that the API container is running.");
  }

  if (!response.ok) throw new Error(await errorFrom(response));
  if (!response.body) throw new Error("The server returned no stream.");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let final: ChatResponse | null = null;

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // Frames are separated by a blank line; a partial tail stays in the buffer.
      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const frame = parseFrame(buffer.slice(0, boundary).replace(/\r/g, ""));
        buffer = buffer.slice(boundary + 2);
        boundary = buffer.indexOf("\n\n");
        if (!frame) continue;

        if (frame.event === "token") {
          onToken((JSON.parse(frame.data) as { delta: string }).delta);
        } else if (frame.event === "final") {
          final = JSON.parse(frame.data) as ChatResponse;
        } else if (frame.event === "error") {
          throw new Error((JSON.parse(frame.data) as { detail: string }).detail);
        }
      }
    }
  } finally {
    // Stopping mid-answer: release the connection instead of draining it.
    reader.cancel().catch(() => undefined);
  }

  // No `final` means the stream was cut short (server restart, network drop):
  // the tokens shown so far are unsourced, so treat it as a failure.
  if (!final) throw new Error("The answer stream ended before completing.");
  return final;
}
