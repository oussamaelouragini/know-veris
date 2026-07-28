import { useState } from "react";
import { FileText, Loader2, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/state";
import { useToast } from "@/components/ui/toast";
import { friendlyErrorMessage } from "@/lib/apiClient";
import { timeAgo } from "@/lib/format";
import type { Document, DocumentStatus } from "@/types";
import { useDeleteDocument, useDocuments } from "./api";

/** Badge styling per ingestion state; the three in-flight states also spin. */
const STATUS: Record<DocumentStatus, { variant: "default" | "secondary" | "outline" | "warning"; busy: boolean }> = {
  PENDING: { variant: "secondary", busy: true },
  PARSING: { variant: "secondary", busy: true },
  EMBEDDING: { variant: "secondary", busy: true },
  INDEXED: { variant: "default", busy: false },
  FAILED: { variant: "warning", busy: false },
};

/** Where a citation for this document would point (ADR-005): pages or sections. */
function location(doc: Document): string {
  if (doc.page_count != null) return `${doc.page_count} page${doc.page_count === 1 ? "" : "s"}`;
  return doc.mime_type.includes("word") ? "sections" : "—";
}

export function DocumentTable() {
  const { data, isLoading, isError, error, refetch, isFetching } = useDocuments();
  const remove = useDeleteDocument();
  const [pending, setPending] = useState<Document | null>(null);
  const toast = useToast();

  if (isLoading) {
    return (
      <div className="space-y-2">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }
  if (isError) {
    return (
      <ErrorState
        title="Could not load the documents."
        message={friendlyErrorMessage(error)}
        onRetry={() => void refetch()}
        retrying={isFetching}
      />
    );
  }
  if (!data?.length) {
    return (
      <EmptyState
        icon={FileText}
        title="No document indexed yet."
        hint="Drop a PDF or DOCX above — the assistant can only answer from what is indexed."
      />
    );
  }

  function confirmDelete() {
    if (!pending) return;
    const { id, filename } = pending;
    remove.mutate(id, {
      // The row disappears the moment the dialog closes, so a failure has no
      // inline home — it would vanish silently without this.
      onError: (cause) => toast.error(`Could not delete ${filename}: ${friendlyErrorMessage(cause)}`),
      onSuccess: () => toast.success(`${filename} deleted.`),
      onSettled: () => setPending(null),
    });
  }

  return (
    <>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-muted-foreground">
              <th className="py-2 pr-4 font-medium">Document</th>
              <th className="py-2 pr-4 font-medium">Status</th>
              {/* Language / size / date are context, not decisions — dropped on
                  narrow screens so the filename and status stay readable
                  without a horizontal scroll. */}
              <th className="hidden py-2 pr-4 font-medium sm:table-cell">Language</th>
              <th className="hidden py-2 pr-4 font-medium md:table-cell">Size</th>
              <th className="hidden py-2 pr-4 font-medium md:table-cell">Uploaded</th>
              <th className="py-2 font-medium sr-only">Actions</th>
            </tr>
          </thead>
          <tbody>
            {data.map((doc) => {
              const status = STATUS[doc.status];
              return (
                <tr key={doc.id} className="border-b border-border last:border-0">
                  <td className="max-w-[22rem] py-2 pr-4">
                    <p className="truncate font-medium" title={doc.filename}>
                      {doc.filename}
                    </p>
                    {doc.status === "FAILED" && doc.error_message && (
                      <p className="truncate text-xs text-destructive" title={doc.error_message}>
                        {doc.error_message}
                      </p>
                    )}
                    <p className="text-xs text-muted-foreground md:hidden">
                      {timeAgo(doc.created_at)}
                    </p>
                  </td>
                  <td className="py-2 pr-4">
                    <Badge variant={status.variant} className="gap-1">
                      {status.busy && <Loader2 className="size-3 animate-spin" />}
                      {doc.status}
                    </Badge>
                  </td>
                  <td className="hidden py-2 pr-4 uppercase text-muted-foreground sm:table-cell">
                    {doc.language ?? "—"}
                  </td>
                  <td className="hidden py-2 pr-4 text-muted-foreground md:table-cell">
                    {location(doc)}
                  </td>
                  <td className="hidden py-2 pr-4 text-muted-foreground md:table-cell">
                    {timeAgo(doc.created_at)}
                  </td>
                  <td className="py-2 text-right">
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Delete ${doc.filename}`}
                      onClick={() => setPending(doc)}
                    >
                      <Trash2 className="text-muted-foreground" />
                    </Button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <ConfirmDialog
        open={pending !== null}
        title="Delete this document?"
        description={
          pending
            ? `"${pending.filename}" and all its indexed chunks will be removed. Answers can no longer cite it.`
            : undefined
        }
        busy={remove.isPending}
        onCancel={() => setPending(null)}
        onConfirm={confirmDelete}
      />
    </>
  );
}
