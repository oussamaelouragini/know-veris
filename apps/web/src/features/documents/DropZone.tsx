import { useRef, useState } from "react";
import { UploadCloud } from "lucide-react";

import { cn } from "@/lib/utils";

const ACCEPT = ".pdf,.docx";

/**
 * Drag & drop (or click) upload target. It only hands files upward — uploading,
 * error mapping and cache invalidation belong to the page, so this stays a dumb,
 * reusable surface.
 *
 * Only PDF and DOCX are accepted; the backend enforces this too (415), the
 * filter here just avoids a pointless round trip. Rejected names are handed
 * back rather than dropped: dragging in a folder of mixed files and seeing
 * nothing happen reads as a broken drop zone, not as a filter doing its job.
 */
export function DropZone({
  onFiles,
  onRejected,
  disabled = false,
}: {
  onFiles: (files: File[]) => void;
  onRejected?: (filenames: string[]) => void;
  disabled?: boolean;
}) {
  const [over, setOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function accept(list: FileList | null) {
    const all = Array.from(list ?? []);
    const files = all.filter((file) => /\.(pdf|docx)$/i.test(file.name));
    const rejected = all.filter((file) => !files.includes(file)).map((file) => file.name);
    if (rejected.length) onRejected?.(rejected);
    if (files.length) onFiles(files);
  }

  return (
    <div
      role="button"
      tabIndex={0}
      aria-disabled={disabled}
      onClick={() => !disabled && inputRef.current?.click()}
      onKeyDown={(e) => {
        if (!disabled && (e.key === "Enter" || e.key === " ")) inputRef.current?.click();
      }}
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        if (!disabled) accept(e.dataTransfer.files);
      }}
      className={cn(
        "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-8 text-center transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        over ? "border-primary bg-accent" : "border-border hover:border-primary/50",
        disabled && "pointer-events-none opacity-60",
      )}
    >
      <UploadCloud className="size-6 text-muted-foreground" />
      <p className="text-sm font-medium">Drop PDF or DOCX files here</p>
      <p className="text-xs text-muted-foreground">or click to choose — indexing starts immediately</p>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        multiple
        className="hidden"
        onChange={(e) => {
          accept(e.target.files);
          e.target.value = ""; // let the same file be re-selected after an error
        }}
      />
    </div>
  );
}
