export type Citation = {
  marker: string;
  chunk_id: string;
  document_id: string;
  filename: string;
  page_number: number | null;
  section_title: string | null;
  score: number;
};

export type ChatResponse = {
  conversation_id: string;
  message_id: string;
  answer: string;
  language: string | null;
  refused: boolean;
  unverified: boolean;
  model_used: string | null;
  latency_ms: number | null;
  citations: Citation[];
};

export type UserRole = "employee" | "admin";

export type Conversation = {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
};

/** Ingestion state machine (backend `DocumentStatus`): PENDING → PARSING → EMBEDDING → INDEXED | FAILED. */
export type DocumentStatus = "PENDING" | "PARSING" | "EMBEDDING" | "INDEXED" | "FAILED";

export type Document = {
  id: string;
  filename: string;
  mime_type: string;
  page_count: number | null;
  language: string | null;
  status: DocumentStatus;
  error_message: string | null;
  created_at: string;
};

/** A Keycloak account as listed in the admin screen — identity lives in Keycloak (ADR-006). */
export type AdminUser = {
  id: string;
  username: string;
  email: string | null;
  enabled: boolean;
  first_name: string | null;
  last_name: string | null;
};

export type AdminUserCreate = {
  username: string;
  email: string;
  first_name: string;
  last_name: string;
};

/** Returned once on creation — the temporary password is never retrievable again. */
export type AdminUserCreated = {
  id: string;
  username: string;
  email: string;
  temporary_password: string;
};

export type PasswordReset = { temporary_password: string };
