"use client";

import { useMemo, useState } from "react";
import type { Health, SchemaInfo } from "@/lib/types";

interface Props {
  schema: SchemaInfo | null;
  health: Health | null;
  onAsk: (q: string) => void;
  open: boolean;
  onClose: () => void;
}

export default function Sidebar({ schema, health, onAsk, open, onClose }: Props) {
  const [filter, setFilter] = useState("");
  const cols = useMemo(() => {
    const f = filter.toLowerCase();
    return (schema?.columns || []).filter(
      (c) => !f || c.name.includes(f) || c.description.toLowerCase().includes(f),
    );
  }, [schema, filter]);

  return (
    <aside className={`sidebar ${open ? "open" : ""}`} aria-label="Data and examples">
      <button className="sidebar-close link" onClick={onClose}>
        Close
      </button>

      <section>
        <h2>Try asking</h2>
        <ul className="samples">
          {(schema?.sample_questions || []).map((q) => (
            <li key={q}>
              <button
                onClick={() => {
                  onAsk(q);
                  onClose();
                }}
              >
                {q}
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section className="columns-section">
        <h2>
          What&rsquo;s in <code>{schema?.table || "loan_portfolio"}</code>
        </h2>
        {schema && <p className="table-desc">{schema.description}</p>}
        <input
          className="col-filter"
          type="search"
          placeholder="Find a column"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          aria-label="Find a column"
        />
        <ul className="columns">
          {cols.map((c) => (
            <li key={c.name}>
              <details>
                <summary>
                  <span className="col-name">{c.name}</span>
                  <span className="col-type">{c.type}</span>
                </summary>
                {c.description && <p>{c.description}</p>}
                {c.values.length > 0 && <p className="col-values">{c.values.join(", ")}</p>}
              </details>
            </li>
          ))}
        </ul>
      </section>

      <footer className="status">
        <span className={`dot ${health?.database ? "ok" : health ? "bad" : ""}`} aria-hidden />
        {health ? (health.database ? "Database connected" : "Database not reachable") : "Checking connection…"}
        {health?.model && <span className="model">Model: {health.model}</span>}
      </footer>
    </aside>
  );
}
