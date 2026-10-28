"""Integration tests against the real Postgres (skipped if it is not running)."""
import pytest
from fastapi.testclient import TestClient

from app import main
from app.agent import TextToSQLAgent
from app.executor import QueryExecutionError
from app.semantic import load_semantic_layer
from app.store import LogStore
from app.validator import validate_sql
from conftest import FakeLLM, action_reply, sql_reply


# ---------- database safety (layers 2 and 3) ----------
@pytest.mark.parametrize("sql", [
    "DELETE FROM loan_portfolio",
    "UPDATE loan_portfolio SET dpd = 0",
    "CREATE TABLE hack (a int)",
    "DROP TABLE loan_portfolio",
])
def test_database_rejects_writes_even_without_validator(real_executor, sql):
    """Bypasses the validator on purpose: the read-only role/transaction must still refuse."""
    with pytest.raises(QueryExecutionError):
        real_executor.run(sql)
    assert real_executor.run("SELECT COUNT(*) FROM loan_portfolio").row_count == 1


def test_statement_timeout(real_executor):
    with pytest.raises(QueryExecutionError) as e:
        real_executor.run("SET LOCAL statement_timeout = '100ms'; SELECT COUNT(*) FROM loan_portfolio a, loan_portfolio b")
    assert "timeout" in str(e.value).lower() or "cancel" in str(e.value).lower()


def test_semantic_layer_examples_run(real_executor):
    for ex in load_semantic_layer()["examples"]:
        r = real_executor.run(validate_sql(ex["sql"], {"loan_portfolio"}).sql)
        assert r.row_count > 0, ex["question"]


def test_agent_self_corrects_on_real_db(real_executor, settings):
    llm = FakeLLM([
        sql_reply("SELECT product, COUNT(*) FROM loan_portfolio GROUP BY 1"),  # wrong column
        sql_reply("SELECT product_type, COUNT(*) AS loans FROM loan_portfolio GROUP BY 1"),
    ])
    r = TextToSQLAgent(llm, real_executor, settings).run("Loans by product")
    assert r.status == "answered" and r.attempts == 2 and r.row_count == 7
    assert 'column "product" does not exist' in llm.calls[1][-1]["content"]


# ---------- API ----------
@pytest.fixture
def client(real_executor, settings, monkeypatch):
    llm = FakeLLM([sql_reply("SELECT region, COUNT(*) AS loans FROM loan_portfolio GROUP BY 1")])
    main.state.executor = real_executor
    main.state.agent = TextToSQLAgent(llm, real_executor, settings)
    main.state.store = LogStore(settings.log_db_path)
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    main._hits.clear()
    main._daily.clear()
    with TestClient(main.app) as c:
        yield c, llm
    main.state.agent = main.state.store = main.state.executor = None


def test_health(client):
    c, _ = client
    body = c.get("/api/health").json()
    assert body["status"] == "ok" and body["database"] is True


def test_schema_endpoint(client):
    c, _ = client
    body = c.get("/api/schema").json()
    assert body["table"] == "loan_portfolio"
    assert len(body["columns"]) == 33 and body["sample_questions"]


def test_ask_end_to_end(client):
    c, _ = client
    body = c.post("/api/ask", json={"question": "Loans by region"}).json()
    assert body["status"] == "answered", body["steps"]
    assert body["columns"] == ["region", "loans"] and body["row_count"] == 6
    assert body["chart"]["type"] == "bar" and body["query_id"]
    assert [s["name"] for s in body["steps"]][:2] == ["input_guard", "generate_sql#1"]


def test_feedback_roundtrip_and_stats(client):
    c, _ = client
    qid = c.post("/api/ask", json={"question": "Loans by region"}).json()["query_id"]
    assert c.post("/api/feedback", json={"query_id": qid, "rating": 1}).json() == {"ok": True}
    assert c.post("/api/feedback", json={"query_id": "nope", "rating": 1}).status_code == 404
    stats = c.get("/api/stats").json()
    assert stats["queries"] == 1 and stats["feedback"] == 1 and stats["thumbs_up_pct"] == 100.0


def test_request_validation(client):
    c, _ = client
    assert c.post("/api/ask", json={"question": ""}).status_code == 422
    assert c.post("/api/ask", json={}).status_code == 422
    assert c.post("/api/feedback", json={"query_id": "x", "rating": 5}).status_code == 422


def test_rate_limit(client, settings):
    c, llm = client
    settings.rate_limit_per_minute = 2
    llm.replies = [action_reply("refuse", "no")] * 5
    codes = [c.post("/api/ask", json={"question": "hi"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_per_visitor_daily_limit_uses_forwarded_ip(client, settings):
    c, llm = client
    settings.trust_proxy_headers = True
    settings.per_ip_daily_limit = 2
    llm.replies = [action_reply("refuse", "no")] * 10
    a = {"X-Forwarded-For": "1.1.1.1, 10.0.0.1"}
    b = {"X-Forwarded-For": "2.2.2.2"}
    codes_a = [c.post("/api/ask", json={"question": "hi"}, headers=a).status_code for _ in range(3)]
    assert codes_a == [200, 200, 429]
    assert c.post("/api/ask", json={"question": "hi"}, headers=b).status_code == 200  # other visitor unaffected
    r = c.post("/api/ask", json={"question": "hi"}, headers=a)
    assert "questions for today" in r.json()["detail"]


def test_global_daily_limit(client, settings):
    c, llm = client
    settings.trust_proxy_headers = True
    settings.daily_question_limit = 2
    llm.replies = [action_reply("refuse", "no")] * 10
    codes = [c.post("/api/ask", json={"question": "hi"}, headers={"X-Forwarded-For": f"9.9.9.{i}"}).status_code
             for i in range(3)]
    assert codes == [200, 200, 429]
