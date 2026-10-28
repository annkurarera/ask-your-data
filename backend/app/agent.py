"""The Text-to-SQL agent.

Flow: guard input -> generate SQL (LLM) -> validate -> execute -> on failure feed the
error back to the LLM and retry -> summarise (LLM) -> pick chart.
"""
import json
import time
from dataclasses import dataclass, field

from .charts import pick_chart
from .config import Settings
from .executor import QueryExecutionError, SQLExecutor
from .llm import LLMClient, Usage, parse_json_reply
from .prompts import SQL_RETRY, SQL_SYSTEM, SUMMARY_SYSTEM, SUMMARY_USER
from .semantic import allowed_tables, load_semantic_layer, schema_context
from .validator import SQLValidationError, validate_sql


@dataclass
class Step:
    name: str
    status: str  # ok | error | skipped
    ms: int = 0
    detail: str = ""


@dataclass
class AgentResult:
    status: str  # answered | clarify | refused | error
    answer: str = ""
    reasoning: str = ""
    sql: str | None = None
    columns: list[str] = field(default_factory=list)
    rows: list[list] = field(default_factory=list)
    row_count: int = 0
    truncated: bool = False
    total_rows: int | None = None  # true number of matching rows (differs from row_count when capped)
    chart: dict = field(default_factory=lambda: {"type": "table"})
    attempts: int = 0
    steps: list[Step] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    latency_ms: int = 0
    error: str | None = None


def _ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


class TextToSQLAgent:
    def __init__(self, llm: LLMClient, executor: SQLExecutor, settings: Settings):
        self.llm = llm
        self.executor = executor
        self.settings = settings
        layer = load_semantic_layer()
        self.tables = allowed_tables(layer)
        self.system_prompt = SQL_SYSTEM.format(as_of=layer["as_of_date"], schema=schema_context(layer))

    # ---------- public ----------
    def run(self, question: str, history: list[dict] | None = None) -> AgentResult:
        t0 = time.perf_counter()
        res = AgentResult(status="error")
        try:
            self._run(question.strip(), history or [], res)
        except Exception as e:  # never leak a stack trace to the user
            res.status = "error"
            res.error = f"{type(e).__name__}: {e}"
            if "auth" in res.error.lower() or "api_key" in res.error.lower() or "api key" in res.error.lower():
                res.answer = "The language model is not configured. Check LLM_MODEL and the API key in backend/.env."
            else:
                res.answer = "Something went wrong while answering. Please try again."
            res.steps.append(Step("unexpected_error", "error", detail=res.error))
        res.latency_ms = _ms(t0)
        return res

    # ---------- internals ----------
    def _run(self, question: str, history: list[dict], res: AgentResult) -> None:
        s = self.settings

        # 1. Input guard (no LLM call, no cost)
        if not question:
            res.status, res.answer = "refused", "Please type a question about the loan portfolio."
            res.steps.append(Step("input_guard", "error", detail="empty question"))
            return
        if len(question) > s.max_question_chars:
            res.status = "refused"
            res.answer = f"Please keep questions under {s.max_question_chars} characters."
            res.steps.append(Step("input_guard", "error", detail="question too long"))
            return
        res.steps.append(Step("input_guard", "ok"))

        messages = [{"role": "system", "content": self.system_prompt}]
        for turn in history[-s.history_turns:]:
            if turn.get("question") and turn.get("sql"):
                messages.append({"role": "user", "content": f"Question: {turn['question']}"})
                messages.append({"role": "assistant", "content": json.dumps(
                    {"action": "sql", "reasoning": "", "sql": turn["sql"], "message": ""})})
        messages.append({"role": "user", "content": f"Question: {question}"})

        # 2-4. Generate -> validate -> execute, with self-correction
        result = None
        checked = None
        for attempt in range(1, s.max_retries + 2):
            res.attempts = attempt
            t = time.perf_counter()
            reply = self.llm.complete(messages, json_mode=True)
            res.usage.add(reply)
            try:
                plan = parse_json_reply(reply.text)
            except ValueError as e:
                res.steps.append(Step(f"generate_sql#{attempt}", "error", _ms(t), str(e)))
                messages += [{"role": "assistant", "content": reply.text},
                             {"role": "user", "content": SQL_RETRY.format(error="Reply was not valid JSON")}]
                continue

            action = str(plan.get("action", "sql")).lower()
            res.reasoning = plan.get("reasoning", "") or ""
            if action in ("clarify", "refuse"):
                res.status = "clarify" if action == "clarify" else "refused"
                res.answer = plan.get("message") or (
                    "Could you clarify your question?" if action == "clarify"
                    else "I can only answer read-only questions about the loan portfolio.")
                res.steps.append(Step("generate_sql", "skipped", _ms(t), f"model chose to {action}"))
                return

            raw_sql = (plan.get("sql") or "").strip()
            res.steps.append(Step(f"generate_sql#{attempt}", "ok", _ms(t), res.reasoning))
            messages.append({"role": "assistant", "content": reply.text})

            t = time.perf_counter()
            try:
                checked = validate_sql(raw_sql, self.tables, s.max_rows)
            except SQLValidationError as e:
                res.sql = raw_sql
                res.steps.append(Step(f"validate#{attempt}", "error", _ms(t), str(e)))
                messages.append({"role": "user", "content": SQL_RETRY.format(error=f"Blocked by validator: {e}")})
                res.error = str(e)
                continue
            res.sql = checked.sql
            res.steps.append(Step(f"validate#{attempt}", "ok", _ms(t),
                                  f"LIMIT {s.max_rows} applied" if checked.limit_applied else ""))

            t = time.perf_counter()
            try:
                result = self.executor.run(checked.sql)
            except QueryExecutionError as e:
                res.steps.append(Step(f"execute#{attempt}", "error", _ms(t), str(e)))
                messages.append({"role": "user", "content": SQL_RETRY.format(error=f"Database error: {e}")})
                res.error = str(e)
                continue
            res.steps.append(Step(f"execute#{attempt}", "ok", result.duration_ms, f"{result.row_count} rows"))
            res.error = None
            break

        if result is None:
            res.status = "error"
            res.answer = ("I couldn't build a working query for that after "
                          f"{res.attempts} attempts. Try rephrasing or adding detail.")
            return

        res.columns, res.rows, res.row_count = result.columns, result.rows, result.row_count
        res.truncated = bool(checked and checked.limit_applied and result.row_count >= s.max_rows)
        res.total_rows = result.row_count
        if res.truncated and checked.count_sql:
            t = time.perf_counter()
            try:
                res.total_rows = int(self.executor.run(checked.count_sql).rows[0][0])
                res.steps.append(Step("count_total", "ok", _ms(t), f"{res.total_rows} matching rows in total"))
            except Exception as e:  # e.g. timeout: still answer, just without the total
                res.total_rows = None
                res.steps.append(Step("count_total", "error", _ms(t), str(e)))
        res.chart = pick_chart(result.columns, result.rows)

        # 5. Summarise
        t = time.perf_counter()
        if result.row_count == 0:
            res.answer = "No records match this question."
            res.steps.append(Step("summarise", "skipped", 0, "no rows"))
        else:
            res.answer = self._summarise(question, res)
            res.steps.append(Step("summarise", "ok", _ms(t)))
        res.status = "answered"

    def _summarise(self, question: str, res: AgentResult) -> str:
        n = self.settings.summary_rows
        shown = res.rows[:n]
        lines = [" | ".join(res.columns)] + [" | ".join("" if v is None else str(v) for v in r) for r in shown]
        if res.truncated:
            total = (f"{res.total_rows} rows match in total" if res.total_rows is not None
                     else f"more than {res.row_count} rows match (exact total unknown)")
            count_note = f"{total}; the app shows the first {res.row_count}"
        else:
            count_note = f"{res.row_count} rows match in total"
        if res.row_count > n:
            count_note += f"; you can see only the first {len(shown)} below"
        msg = SUMMARY_USER.format(question=question, sql=res.sql, count_note=count_note,
                                  columns=", ".join(res.columns), rows="\n".join(lines))
        reply = self.llm.complete([{"role": "system", "content": SUMMARY_SYSTEM},
                                   {"role": "user", "content": msg}])
        res.usage.add(reply)
        return reply.text.strip()
