import type { AskResponse, HealthResponse } from "./types";

// 后端地址：可建 .env 用 VITE_API_BASE 覆盖
const BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:13080";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail || `请求失败 (${res.status})`);
  }
  return res.json() as Promise<T>;
}

export function ask(question: string): Promise<AskResponse> {
  return request<AskResponse>("/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
}

export function ingest(file: File): Promise<{ inserted: number }> {
  const form = new FormData();
  form.append("file", file);
  return request<{ inserted: number }>("/ingest", {
    method: "POST",
    body: form,
  });
}

export function health(): Promise<HealthResponse> {
  return request<HealthResponse>("/health");
}
