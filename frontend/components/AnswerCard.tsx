"use client";

import { useState } from "react";
import ResultChart from "./ResultChart";
import { sendFeedback } from "@/lib/api";
import { formatCell, humanizeColumn, toCSV } from "@/lib/format";
import type { AskResponse, Turn } from "@/lib/types";

const STAMP: Record<string, string> = {
  refused: "Declined",
  clarify: "Needs detail",
  error: "Not answered",
};

const STEP_LABEL: Record<string, string> = {
  input_guard: "Checked the question",
  generate_sql: "Wrote SQL",
  validate: "Checked SQL is read-only",
  execute: "Ran on the database",
  count_total: "Counted all matching rows",
  summarise: "Wrote the answer",
  unexpected_error: "Stopped by an error",
};

function stepLabel(name: string) {
  const [base, attempt] = name.split("#");
  const label = STEP_LABEL[base] || base;
  return attempt && attempt !== "1" ? `${label} (attempt ${attempt})` : label;
}

const PAGE = 50;

export default function AnswerCard({ turn, onAsk }: { turn: Turn; onAsk: (q: string) => void }) {
  return (
    <article className="turn" data-testid="turn">
      <p className="turn-question">{turn.question}</p>
      {turn.pending && <Working />}
      {turn.error && (
        <div className="card card-error" role="alert">
          <p>{turn.error}</p>
          <button className="link" onClick={() => onAsk(turn.question)}>
            Ask again
          </button>
        </div>
      )}
      {turn.response && <Answer r={turn.response} />}
    </article>
  );
}

function Working() {
  return (
    <div className="card working" aria-live="polite">
      <span className="pulse" aria-hidden />
      Writing and checking a query on 10 lakh loans…
    </div>
  );
}

function Answer({ r }: { r: AskResponse }) {
  const [showSql, setShowSql] = useState(false);
  const [showSteps, setShowSteps] = useState(false);
  const [visible, setVisible] = useState(PAGE);
  const [rating, setRating] = useState<1 | -1 | null>(null);
  const [copied, setCopied] = useState(false);
  const answered = r.status === "answered";

  const rate = async (v: 1 | -1) => {
    setRating(v);
    try {
      await sendFeedback(r.query_id, v);
    } catch {
      setRating(null);
    }
  };

  const copySql = async () => {
    if (!r.sql) return;
    await navigator.clipboard?.writeText(r.sql);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const download = () => {
    const blob = new Blob([toCSV(r.columns, r.rows)], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `ask-your-data-${r.query_id}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <div className={`card ${answered ? "" : "card-stamped"}`} data-status={r.status}>
      {!answered && (
        <span className={`stamp stamp-${r.status}`} data-testid="stamp">
          {STAMP[r.status]}
        </span>
      )}

      <p className="answer" data-testid="answer">
        {r.answer}
      </p>
      {answered && r.reasoning && <p className="assumption">How I read it: {r.reasoning}</p>}

      {answered && r.row_count > 0 && <ResultChart data={r} />}

      {answered && r.row_count > 0 && r.chart.type !== "kpi" && (
        <div className="table-wrap" data-testid="results-table">
          <table>
            <thead>
              <tr>
                {r.columns.map((c, j) => (
                  <th key={c} scope="col" className={typeof r.rows[0]?.[j] === "number" ? "num" : ""}>
                    {humanizeColumn(c)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {r.rows.slice(0, visible).map((row, i) => (
                <tr key={i}>
                  {row.map((v, j) => (
                    <td key={j} className={typeof v === "number" ? "num" : ""}>
                      {formatCell(v, r.columns[j])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {r.row_count > visible && (
            <button className="link more" onClick={() => setVisible((n) => n + PAGE)}>
              Show {Math.min(PAGE, r.row_count - visible)} more of {r.row_count} rows
            </button>
          )}
        </div>
      )}
      {r.truncated && (
        <p className="note" data-testid="truncated-note">
          {r.total_rows
            ? `Showing the first ${r.row_count.toLocaleString("en-IN")} of ${r.total_rows.toLocaleString("en-IN")} matching rows.`
            : `Showing the first ${r.row_count.toLocaleString("en-IN")} rows; more rows match.`}{" "}
          Ask for a count or add a filter to narrow it down.
        </p>
      )}

      <div className="toolbar">
        {r.sql && (
          <button className="tool" aria-expanded={showSql} onClick={() => setShowSql((s) => !s)}>
            {showSql ? "Hide SQL" : "Show SQL"}
          </button>
        )}
        <button className="tool" aria-expanded={showSteps} onClick={() => setShowSteps((s) => !s)}>
          {showSteps ? "Hide steps" : "How it was answered"}
        </button>
        {answered && r.row_count > 0 && (
          <button className="tool" onClick={download}>
            Download CSV
          </button>
        )}
        <span className="spacer" />
        {answered && (
          <span className="feedback" role="group" aria-label="Was this answer right?">
            <button
              className={`thumb ${rating === 1 ? "on" : ""}`}
              aria-pressed={rating === 1}
              aria-label="Answer was right"
              title="Answer was right"
              onClick={() => rate(1)}
              disabled={rating !== null}
            >
              <ThumbIcon />
            </button>
            <button
              className={`thumb down ${rating === -1 ? "on" : ""}`}
              aria-pressed={rating === -1}
              aria-label="Answer was wrong"
              title="Answer was wrong"
              onClick={() => rate(-1)}
              disabled={rating !== null}
            >
              <ThumbIcon />
            </button>
            {rating !== null && <span className="thanks">Feedback saved</span>}
          </span>
        )}
      </div>

      {showSql && r.sql && (
        <div className="sql" data-testid="sql">
          <button className="copy" onClick={copySql}>
            {copied ? "Copied" : "Copy"}
          </button>
          <pre>
            <code>{r.sql}</code>
          </pre>
        </div>
      )}

      {showSteps && (
        <ol className="steps" data-testid="steps">
          {r.steps.map((s, i) => (
            <li key={i} className={`step step-${s.status}`}>
              <span className="step-name">{stepLabel(s.name)}</span>
              <span className="step-ms">{s.ms} ms</span>
              {s.detail && <span className="step-detail">{s.detail}</span>}
            </li>
          ))}
        </ol>
      )}

      <dl className="meta">
        <div>
          <dt>Time</dt>
          <dd>{(r.latency_ms / 1000).toFixed(1)} s</dd>
        </div>
        <div>
          <dt>Attempts</dt>
          <dd>{r.attempts}</dd>
        </div>
        <div>
          <dt>Tokens</dt>
          <dd>{r.tokens.toLocaleString("en-IN")}</dd>
        </div>
        <div>
          <dt>Cost</dt>
          <dd>${r.cost_usd.toFixed(4)}</dd>
        </div>
      </dl>
    </div>
  );
}

function ThumbIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
      <path d="M7 10v11H3V10h4Zm0 0 4-8a3 3 0 0 1 3 3v4h5.5a2 2 0 0 1 2 2.3l-1.4 8A2 2 0 0 1 18 21H7" strokeLinejoin="round" />
    </svg>
  );
}
