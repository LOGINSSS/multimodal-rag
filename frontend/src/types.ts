export interface Source {
  source: string;
  doc_type: string;
  text: string;
}

export interface AskResponse {
  answer: string;
  sources: Source[];
  rewritten: string;
  hyde: string;
}

export interface HealthResponse {
  status: string;
  milvus_ok: boolean;
  rows: number;
  error: string;
}

export type TaskStatusValue = "pending" | "running" | "done" | "failed";

export interface TaskStatus {
  task_id: string;
  status: TaskStatusValue;
  source: string;
  inserted: number;
  error: string;
}

export interface UploadItem {
  id: string;
  name: string;
  status: "submitting" | TaskStatusValue;
  inserted: number;
  error: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  rewritten?: string;
  hyde?: string;
  pending?: boolean;
  error?: string;
}

export type Theme = "light" | "dark";
