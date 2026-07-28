import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import axios from "axios";

import { apiClient, apiErrorDetail } from "@/lib/apiClient";
import type { Document } from "@/types";

const documentsKey = ["documents"] as const;

/** Statuses that mean the BackgroundTask is still working on this document. */
const IN_FLIGHT: Document["status"][] = ["PENDING", "PARSING", "EMBEDDING"];

async function fetchDocuments(): Promise<Document[]> {
  const { data } = await apiClient.get<Document[]>("/documents");
  return data;
}

/**
 * The document list, polled every 5 s while anything is still being ingested
 * (PLAN Flow A). Upload returns 202 immediately and parsing/embedding runs in a
 * BackgroundTask, so the status column is the only way the admin sees progress.
 * Polling stops on its own once everything is INDEXED or FAILED.
 */
export function useDocuments() {
  return useQuery({
    queryKey: documentsKey,
    queryFn: fetchDocuments,
    refetchInterval: (query) =>
      query.state.data?.some((doc) => IN_FLIGHT.includes(doc.status)) ? 5000 : false,
  });
}

async function uploadDocument(file: File): Promise<Document> {
  const form = new FormData();
  form.append("file", file);
  // The Content-Type override is required, not cosmetic: the shared instance
  // defaults to application/json, and Axios v1 converts a FormData body to JSON
  // whenever the request declares a JSON content type — the API then sees
  // {"file":{}} and answers 422. Declaring multipart keeps the FormData intact;
  // the browser rewrites the header with the real boundary.
  const { data } = await apiClient.post<Document>("/documents", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

/** Human-readable reason for the statuses the upload endpoint rejects. */
export function uploadErrorMessage(error: unknown, filename: string): string {
  if (axios.isAxiosError(error)) {
    if (error.response?.status === 409) return `${filename}: already indexed (identical content).`;
    if (error.response?.status === 415) return `${filename}: only PDF and DOCX are accepted.`;
    if (error.response?.status === 403) return `${filename}: admin role required.`;
    const detail = apiErrorDetail(error);
    if (detail) return `${filename}: ${detail}`;
  }
  return `${filename}: ${error instanceof Error ? error.message : String(error)}`;
}

/** Upload one file (202 Accepted), then refresh the list so polling picks it up. */
export function useUploadDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: uploadDocument,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: documentsKey }),
  });
}

async function deleteDocument(id: string): Promise<void> {
  await apiClient.delete(`/documents/${id}`);
}

/** Delete a document — cascades to its chunks server-side. */
export function useDeleteDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteDocument,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: documentsKey }),
  });
}
