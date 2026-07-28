import { FileText } from "lucide-react";

import type { Citation } from "@/types";

/**
 * One grounding source under an answer: the document, its exact location
 * (page for PDFs, section for DOCX — ADR-005) and the retrieval score.
 *
 * This card is the visible half of the project's core promise: every answer is
 * traceable to a passage of a real document. Always laid out LTR — a filename
 * and a page number are not prose, and mirroring them in an Arabic conversation
 * would only make them harder to read.
 */
export function SourceCard({ citation }: { citation: Citation }) {
  const location =
    citation.page_number != null
      ? `page ${citation.page_number}`
      : citation.section_title
        ? `§ ${citation.section_title}`
        : null;
  const percent = Math.round(Math.max(0, Math.min(1, citation.score)) * 100);

  return (
    <div dir="ltr" className="rounded-md border border-border bg-muted/40 p-2.5">
      <div className="flex items-start gap-2">
        <FileText className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs font-medium" title={citation.filename}>
            <span className="text-muted-foreground">[{citation.marker}]</span>{" "}
            {citation.filename}
          </p>
          {location && <p className="truncate text-xs text-muted-foreground">{location}</p>}
        </div>
        <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
          {citation.score.toFixed(2)}
        </span>
      </div>
      {/* Relevance bar — the same score the refusal guardrail thresholds on. */}
      <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-border">
        <div className="h-full rounded-full bg-primary" style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}
