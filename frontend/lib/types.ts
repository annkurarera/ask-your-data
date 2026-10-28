export type Status = "answered" | "clarify" | "refused" | "error";

export interface Step {
  name: string;
  status: "ok" | "error" | "skipped";
  ms: number;
  detail: string;
}

export interface Chart {
  type: "kpi" | "line" | "bar" | "table";
  x?: string;
  y?: string[];
}

export interface AskResponse {
  query_id: string;
  status: Status;
  answer: string;
  reasoning: string;
  sql: string | null;
  columns: string[];
  rows: (string | number | boolean | null)[][];
  row_count: number;
  truncated: boolean;
  total_rows?: number | null;
  chart: Chart;
  attempts: number;
  steps: Step[];
  latency_ms: number;
  cost_usd: number;
  tokens: number;
}

export interface Column {
  name: string;
  type: string;
  description: string;
  values: string[];
}

export interface SchemaInfo {
  table: string;
  description: string;
  as_of_date: string;
  columns: Column[];
  sample_questions: string[];
}

export interface Health {
  status: "ok" | "degraded";
  database: boolean;
  model: string;
}

export interface Turn {
  id: string;
  question: string;
  response?: AskResponse;
  error?: string;
  pending: boolean;
}
