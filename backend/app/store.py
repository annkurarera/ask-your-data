"""Query log and user feedback, stored in a local SQLite file.
Kept separate from the read-only analytics database on purpose."""
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone


class LogStore:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        with self._conn() as c:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS queries (
                    id TEXT PRIMARY KEY, ts TEXT, question TEXT, status TEXT, sql TEXT,
                    attempts INTEGER, row_count INTEGER, latency_ms INTEGER,
                    llm_calls INTEGER, input_tokens INTEGER, output_tokens INTEGER,
                    cost_usd REAL, error TEXT, steps TEXT
                );
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, query_id TEXT, ts TEXT,
                    rating INTEGER, comment TEXT
                );
                """
            )

    def _conn(self):
        return sqlite3.connect(self.path, timeout=10)

    def log_query(self, question: str, result) -> str:
        qid = uuid.uuid4().hex[:12]
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT INTO queries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    qid, datetime.now(timezone.utc).isoformat(), question, result.status, result.sql,
                    result.attempts, result.row_count, result.latency_ms, result.usage.calls,
                    result.usage.input_tokens, result.usage.output_tokens, round(result.usage.cost_usd, 6),
                    result.error, json.dumps([s.__dict__ for s in result.steps]),
                ),
            )
        return qid

    def add_feedback(self, query_id: str, rating: int, comment: str | None) -> bool:
        with self._lock, self._conn() as c:
            if not c.execute("SELECT 1 FROM queries WHERE id = ?", (query_id,)).fetchone():
                return False
            c.execute(
                "INSERT INTO feedback (query_id, ts, rating, comment) VALUES (?,?,?,?)",
                (query_id, datetime.now(timezone.utc).isoformat(), rating, comment),
            )
        return True

    def stats(self) -> dict:
        with self._conn() as c:
            q = c.execute(
                """SELECT COUNT(*), SUM(status = 'answered'), AVG(latency_ms),
                          COALESCE(SUM(cost_usd), 0), AVG(attempts)
                   FROM queries"""
            ).fetchone()
            f = c.execute("SELECT COUNT(*), SUM(rating > 0) FROM feedback").fetchone()
        total = q[0] or 0
        return {
            "queries": total,
            "answered_pct": round(100 * (q[1] or 0) / total, 1) if total else None,
            "avg_latency_ms": round(q[2]) if q[2] else None,
            "total_cost_usd": round(q[3], 4),
            "avg_attempts": round(q[4], 2) if q[4] else None,
            "feedback": f[0] or 0,
            "thumbs_up_pct": round(100 * (f[1] or 0) / f[0], 1) if f[0] else None,
        }
