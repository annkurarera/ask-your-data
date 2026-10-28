"""Runs validated SQL against Postgres in a read-only transaction with a timeout."""
import datetime as dt
import time
from dataclasses import dataclass
from decimal import Decimal

from psycopg_pool import ConnectionPool

from .config import Settings


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[list]
    row_count: int
    duration_ms: int


class QueryExecutionError(RuntimeError):
    """Database rejected or failed the query. The message is fed back to the LLM."""


def _to_json_value(v):
    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() and abs(v) < 2**53 else float(v)
    if isinstance(v, dt.datetime):
        return v.date().isoformat() if v.time() == dt.time(0) else v.isoformat()
    if isinstance(v, (dt.date, dt.time)):
        return v.isoformat()
    if isinstance(v, dt.timedelta):
        return str(v)
    return v


class SQLExecutor:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.pool = ConnectionPool(
            settings.database_url,
            min_size=1,
            max_size=10,
            open=False,
            kwargs={"options": f"-c statement_timeout={settings.statement_timeout_ms}"},
        )

    def open(self) -> None:
        self.pool.open(wait=True, timeout=10)

    def close(self) -> None:
        self.pool.close()

    def ping(self) -> bool:
        try:
            with self.pool.connection(timeout=5) as conn:
                conn.execute("SELECT 1")
            return True
        except Exception:
            return False

    def run(self, sql: str) -> QueryResult:
        start = time.perf_counter()
        try:
            with self.pool.connection(timeout=10) as conn:
                with conn.transaction():
                    conn.execute("SET TRANSACTION READ ONLY")
                    cur = conn.execute(sql)
                    columns = [d.name for d in cur.description] if cur.description else []
                    rows = [[_to_json_value(v) for v in row] for row in cur.fetchall()]
                    # Abort instead of commit: nothing a query does can ever persist
                    raise _Rollback(columns, rows)
        except _Rollback as r:
            columns, rows = r.columns, r.rows
        except Exception as e:  # psycopg errors, timeouts, pool errors
            msg = str(e).strip().splitlines()[0] if str(e).strip() else type(e).__name__
            raise QueryExecutionError(msg) from e
        return QueryResult(columns, rows, len(rows), int((time.perf_counter() - start) * 1000))


class _Rollback(Exception):
    def __init__(self, columns, rows):
        super().__init__("rollback")
        self.columns, self.rows = columns, rows
