import { useState } from "react";
import { Loader2 } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useToast } from "@/components/ui/toast";
import { DocumentTable } from "./DocumentTable";
import { DropZone } from "./DropZone";
import { uploadErrorMessage, useUploadDocument } from "./api";

/**
 * Admin document management (PLAN Flow A). Upload returns 202 immediately and
 * the ingestion runs in a BackgroundTask, so the table below polls until every
 * document reaches INDEXED or FAILED.
 *
 * Files are uploaded one at a time rather than in parallel: ingestion is
 * CPU-bound (parse → embed via BGE-M3) on a machine with no GPU, and firing
 * several at once only makes them all slower.
 */
export function DocumentsPage() {
  const upload = useUploadDocument();
  const [errors, setErrors] = useState<string[]>([]);
  const [progress, setProgress] = useState<{ name: string; index: number; total: number } | null>(
    null,
  );
  const toast = useToast();

  async function handleFiles(files: File[]) {
    setErrors([]);
    const failures: string[] = [];
    let accepted = 0;
    for (const [index, file] of files.entries()) {
      // Which file, and how far into the batch — a 10-file drop otherwise looks
      // stuck on whichever name happens to be showing.
      setProgress({ name: file.name, index: index + 1, total: files.length });
      try {
        await upload.mutateAsync(file);
        accepted += 1;
      } catch (error) {
        failures.push(uploadErrorMessage(error, file.name));
      }
    }
    setProgress(null);
    setErrors(failures);
    if (accepted) {
      toast.success(
        `${accepted} file${accepted === 1 ? "" : "s"} accepted — indexing runs in the background.`,
      );
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-4 p-4 sm:space-y-6 sm:p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Documents</h1>
        <p className="text-sm text-muted-foreground">
          Upload the procedures the assistant is allowed to answer from.
        </p>
      </div>

      <Card>
        <CardContent className="space-y-3 pt-6">
          <DropZone
            onFiles={handleFiles}
            onRejected={(names) =>
              toast.error(
                `Skipped ${names.length === 1 ? names[0] : `${names.length} files`} — only PDF and DOCX can be indexed.`,
              )
            }
            disabled={progress !== null}
          />
          {progress && (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" />
              Uploading {progress.name}
              {progress.total > 1 && ` (${progress.index} of ${progress.total})`}…
            </p>
          )}
          {errors.map((message) => (
            <p key={message} className="rounded-md bg-destructive/10 p-2 text-sm text-destructive">
              {message}
            </p>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Indexed documents</CardTitle>
          <CardDescription>
            Status refreshes every 5 s while a document is being parsed and embedded.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <DocumentTable />
        </CardContent>
      </Card>
    </div>
  );
}
