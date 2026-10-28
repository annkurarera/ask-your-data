"""FastAPI app: /api/health, /api/schema, /api/ask, /api/feedback, /api/stats"""
import logging
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .agent import TextToSQLAgent
from .config import get_settings
from .executor import SQLExecutor
from .llm import LiteLLMClient
from .semantic import column_summary, load_semantic_layer
from .store import LogStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("ask-your-data")


# ---------- request / response models ----------
class Turn(BaseModel):
    question: str = Field(max_length=2000)
    sql: str | None = Field(default=None, max_length=10_000)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    history: list[Turn] = Field(default_factory=list, max_length=10)


class StepOut(BaseModel):
    name: str
    status: str
    ms: int
    detail: str


class AskResponse(BaseModel):
    query_id: str
    status: str
    answer: str
    reasoning: str
    sql: str | None
    columns: list[str]
    rows: list[list]
    row_count: int
    truncated: bool
    total_rows: int | None
    chart: dict
    attempts: int
    steps: list[StepOut]
    latency_ms: int
    cost_usd: float
    tokens: int


class FeedbackRequest(BaseModel):
    query_id: str = Field(min_length=1, max_length=40)
    rating: int = Field(ge=-1, le=1)
    comment: str | None = Field(default=None, max_length=1000)


# ---------- app state ----------
class AppState:
    executor: SQLExecutor | None = None
    agent: TextToSQLAgent | None = None
    store: LogStore | None = None


state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    created_executor = None
    if state.agent is None:  # tests inject their own agent
        state.executor = created_executor = SQLExecutor(settings)
        try:
            state.executor.open()
        except Exception as e:
            log.warning("Database not reachable at startup: %s", e)
        state.agent = TextToSQLAgent(LiteLLMClient(settings), state.executor, settings)
        # Warm-up: load LiteLLM now, so the first user question isn't slow
        t0 = time.perf_counter()
        import litellm  # noqa: F401
        log.info("Agent ready with model %s (LLM client loaded in %.1fs)",
                 settings.llm_model, time.perf_counter() - t0)
    if state.store is None:
        state.store = LogStore(settings.log_db_path)
    yield
    if created_executor:
        created_executor.close()


app = FastAPI(title="Ask Your Data", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",")],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ---------- rate limits (per minute, per visitor per day, everyone per day) ----------
_hits: dict[str, deque] = defaultdict(deque)
_daily: dict[str, int] = defaultdict(int)  # keys: "<date>|<ip>" and "<date>|ALL"


def client_ip(request: Request) -> str:
    """Real visitor IP. Behind a proxy (Render, Vercel) the first X-Forwarded-For entry is the visitor."""
    if get_settings().trust_proxy_headers:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(request: Request) -> None:
    s = get_settings()
    ip = client_ip(request)
    now = time.time()

    q = _hits[ip]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= s.rate_limit_per_minute:
        raise HTTPException(status_code=429, detail="Too many questions. Please wait a minute.")

    today = time.strftime("%Y-%m-%d", time.gmtime(now))
    if s.daily_question_limit and _daily[f"{today}|ALL"] >= s.daily_question_limit:
        raise HTTPException(status_code=429,
                            detail="This public demo has reached today's question limit. Please try again tomorrow.")
    if s.per_ip_daily_limit and _daily[f"{today}|{ip}"] >= s.per_ip_daily_limit:
        raise HTTPException(status_code=429,
                            detail=f"You've used all {s.per_ip_daily_limit} questions for today. Please come back tomorrow.")

    q.append(now)
    _daily[f"{today}|ALL"] += 1
    _daily[f"{today}|{ip}"] += 1


# ---------- routes ----------
@app.get("/api/health")
def health():
    db_ok = bool(state.executor and state.executor.ping())
    return {"status": "ok" if db_ok else "degraded", "database": db_ok, "model": get_settings().llm_model}


@app.get("/api/schema")
def schema():
    layer = load_semantic_layer()
    return {
        "table": layer["table"]["name"],
        "description": layer["table"]["description"].strip(),
        "as_of_date": layer["as_of_date"],
        "columns": column_summary(layer),
        "sample_questions": layer.get("sample_questions", []),
    }


@app.post("/api/ask", response_model=AskResponse, dependencies=[Depends(rate_limit)])
def ask(req: AskRequest):
    result = state.agent.run(req.question, [t.model_dump() for t in req.history])
    query_id = state.store.log_query(req.question, result)
    log.info("q=%s status=%s attempts=%s rows=%s latency=%sms cost=$%.5f",
             query_id, result.status, result.attempts, result.row_count, result.latency_ms, result.usage.cost_usd)
    return AskResponse(
        query_id=query_id,
        status=result.status,
        answer=result.answer,
        reasoning=result.reasoning,
        sql=result.sql,
        columns=result.columns,
        rows=result.rows,
        row_count=result.row_count,
        truncated=result.truncated,
        total_rows=result.total_rows,
        chart=result.chart,
        attempts=result.attempts,
        steps=[StepOut(**s.__dict__) for s in result.steps],
        latency_ms=result.latency_ms,
        cost_usd=round(result.usage.cost_usd, 6),
        tokens=result.usage.input_tokens + result.usage.output_tokens,
    )


@app.post("/api/feedback")
def feedback(req: FeedbackRequest):
    if not state.store.add_feedback(req.query_id, req.rating, req.comment):
        raise HTTPException(status_code=404, detail="Unknown query_id")
    return {"ok": True}


@app.get("/api/stats")
def stats():
    return state.store.stats()
