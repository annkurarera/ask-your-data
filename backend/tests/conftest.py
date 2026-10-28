import json
import os

import pytest

from app.config import Settings
from app.executor import QueryExecutionError, QueryResult, SQLExecutor
from app.llm import LLMResponse

TEST_DB_URL = os.getenv("DATABASE_URL", "postgresql://nl2sql_reader:reader_pw@localhost:5432/bankdb")


def sql_reply(sql: str, reasoning: str = "plan") -> str:
    return json.dumps({"action": "sql", "reasoning": reasoning, "sql": sql, "message": ""})


def action_reply(action: str, message: str) -> str:
    return json.dumps({"action": action, "reasoning": "", "sql": "", "message": message})


class FakeLLM:
    """Returns scripted replies in order and records every call."""

    def __init__(self, replies: list[str], summary: str = "Fake summary."):
        self.replies = list(replies)
        self.summary = summary
        self.calls: list[list[dict]] = []

    def complete(self, messages, json_mode=False):
        self.calls.append(list(messages))  # copy: the agent keeps appending to its list
        if not json_mode:  # summary call
            return LLMResponse(self.summary, 50, 20, 0.0001)
        if not self.replies:
            raise AssertionError("FakeLLM ran out of scripted replies")
        return LLMResponse(self.replies.pop(0), 1000, 100, 0.001)

    @property
    def sql_calls(self) -> int:
        return sum(1 for m in self.calls if m[0]["content"].startswith("You are a senior analyst"))


class FakeExecutor:
    """Pretends to be the database: returns a fixed result, or errors for SQL containing a marker."""

    def __init__(self, columns=None, rows=None, fail_if_contains: str | None = None):
        self.columns = columns or ["product_type", "loans"]
        self.rows = rows if rows is not None else [["Home Loan", 10], ["Gold Loan", 5]]
        self.fail_if_contains = fail_if_contains
        self.total = 5000
        self.executed: list[str] = []

    def run(self, sql: str) -> QueryResult:
        self.executed.append(sql)
        if self.fail_if_contains and self.fail_if_contains in sql:
            raise QueryExecutionError(f'column "{self.fail_if_contains}" does not exist')
        if sql.startswith("SELECT COUNT(*) AS total_rows FROM ("):
            return QueryResult(["total_rows"], [[self.total]], 1, 2)
        return QueryResult(self.columns, self.rows, len(self.rows), 3)

    def ping(self) -> bool:
        return True


@pytest.fixture
def settings(tmp_path):
    return Settings(database_url=TEST_DB_URL, log_db_path=str(tmp_path / "logs.db"), rate_limit_per_minute=1000)


@pytest.fixture(scope="session")
def real_executor():
    s = Settings(database_url=TEST_DB_URL)
    ex = SQLExecutor(s)
    try:
        ex.open()
    except Exception:
        pytest.skip("Postgres not reachable; start it with `docker compose up -d` to run DB tests")
    if not ex.ping():
        pytest.skip("Postgres not reachable")
    yield ex
    ex.close()
