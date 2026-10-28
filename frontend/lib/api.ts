import type { AskResponse, Health, SchemaInfo } from "./types";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    });
  } catch {
    throw new Error(`Can't reach the API at ${API_URL}. Check that the backend is running.`);
  }
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* keep the default message */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const getHealth = () => request<Health>("/api/health");
export const getSchema = () => request<SchemaInfo>("/api/schema");

export const ask = (question: string, history: { question: string; sql: string | null }[]) =>
  request<AskResponse>("/api/ask", { method: "POST", body: JSON.stringify({ question, history }) });

export const sendFeedback = (query_id: string, rating: 1 | -1) =>
  request<{ ok: boolean }>("/api/feedback", { method: "POST", body: JSON.stringify({ query_id, rating }) });
