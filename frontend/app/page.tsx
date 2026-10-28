"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import AnswerCard from "@/components/AnswerCard";
import Sidebar from "@/components/Sidebar";
import { ask, getHealth, getSchema } from "@/lib/api";
import type { Health, SchemaInfo, Turn } from "@/lib/types";

const MAX_CHARS = 500;

export default function Home() {
  const [schema, setSchema] = useState<SchemaInfo | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const busy = turns.some((t) => t.pending);

  // Free hosting sleeps when idle: keep checking until the backend is awake (up to ~3 minutes)
  const [waking, setWaking] = useState(false);
  useEffect(() => {
    let cancelled = false;
    const slow = setTimeout(() => !cancelled && setWaking(true), 3000);
    (async () => {
      for (let attempt = 0; attempt < 36 && !cancelled; attempt++) {
        try {
          const h = await getHealth();
          if (cancelled) return;
          setHealth(h);
          if (h.database) {
            getSchema().then(setSchema).catch(() => setSchema(null));
            break;
          }
        } catch {
          if (attempt === 0 && !cancelled) setHealth(null);
        }
        await new Promise((r) => setTimeout(r, 5000));
      }
      if (!cancelled) {
        clearTimeout(slow);
        setWaking(false);
      }
    })();
    return () => {
      cancelled = true;
      clearTimeout(slow);
    };
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  const submit = useCallback(
    async (q: string) => {
      const question = q.trim();
      if (!question || busy) return;
      const id = crypto.randomUUID();
      // Follow-up context: the last 3 answered turns
      const history = turns
        .filter((t) => t.response?.status === "answered")
        .slice(-3)
        .map((t) => ({ question: t.question, sql: t.response!.sql }));
      setTurns((ts) => [...ts, { id, question, pending: true }]);
      setInput("");
      try {
        const response = await ask(question, history);
        setTurns((ts) => ts.map((t) => (t.id === id ? { ...t, pending: false, response } : t)));
      } catch (e) {
        const error = e instanceof Error ? e.message : "Something went wrong.";
        setTurns((ts) => ts.map((t) => (t.id === id ? { ...t, pending: false, error } : t)));
      }
      inputRef.current?.focus();
    },
    [busy, turns],
  );

  const onKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit(input);
    }
  };

  const asOf = schema
    ? new Date(schema.as_of_date + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" })
    : "30 September 2026";

  return (
    <div className="shell">
      <header className="masthead">
        <div className="masthead-inner">
          <div>
            <h1>Ask Your Data</h1>
            <p className="tagline">
              Plain-English questions on a 10 lakh–loan retail book, answered with SQL you can check. Data as of {asOf}.
            </p>
          </div>
          <button className="menu link" onClick={() => setSidebarOpen(true)}>
            Examples and columns
          </button>
        </div>
      </header>

      <div className="body">
        <Sidebar schema={schema} health={health} onAsk={submit} open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
        {sidebarOpen && <div className="scrim" onClick={() => setSidebarOpen(false)} aria-hidden />}

        <main className="thread">
          {waking && !health?.database && (
            <p className="waking" role="status" data-testid="waking">
              Starting the demo server. Free hosting sleeps when no one is using it, so the first load can take up to a
              minute.
            </p>
          )}
          {turns.length === 0 ? (
            <section className="empty">
              <h2>Ask about NPAs, disbursements, branches or customers</h2>
              <p>
                The assistant writes a read-only PostgreSQL query, checks it, runs it on the loan book and explains the
                result. Follow-up questions use the earlier answers as context. All data is synthetic.
              </p>
              <div className="starters">
                {(schema?.sample_questions || []).slice(0, 4).map((q) => (
                  <button key={q} onClick={() => submit(q)}>
                    {q}
                  </button>
                ))}
              </div>
            </section>
          ) : (
            turns.map((t) => <AnswerCard key={t.id} turn={t} onAsk={submit} />)
          )}
          <div ref={endRef} />

          <form
            className="composer"
            onSubmit={(e) => {
              e.preventDefault();
              submit(input);
            }}
          >
            <label htmlFor="q" className="sr-only">
              Your question
            </label>
            <textarea
              id="q"
              ref={inputRef}
              rows={2}
              value={input}
              maxLength={MAX_CHARS}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKey}
              placeholder={turns.length ? "Ask a follow-up, e.g. now only for Tier 3 cities" : "e.g. Which 10 branches have the highest NPA %?"}
              disabled={busy}
            />
            <div className="composer-row">
              <span className="hint">
                {input.length > MAX_CHARS - 80 ? `${MAX_CHARS - input.length} characters left` : "Enter to ask, Shift+Enter for a new line"}
              </span>
              <button type="submit" className="primary" disabled={busy || !input.trim()}>
                {busy ? "Answering…" : "Ask"}
              </button>
            </div>
          </form>
        </main>
      </div>
    </div>
  );
}
