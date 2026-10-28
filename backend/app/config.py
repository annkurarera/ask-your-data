"""App settings, read from environment variables or backend/.env."""
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent

# Put every value from backend/.env into the environment, so LiteLLM can find
# provider keys such as OPENAI_API_KEY or AZURE_API_KEY.
load_dotenv(BACKEND_DIR / ".env")

# Use LiteLLM's bundled price list instead of downloading it from GitHub on the first
# call (that download made the first question after a restart take ~30 seconds).
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    # Database: the app connects with the READ-ONLY role
    database_url: str = "postgresql://nl2sql_reader:reader_pw@localhost:5432/bankdb"
    statement_timeout_ms: int = 15_000

    # LLM (any LiteLLM model string):
    #   OpenAI:  gpt-4.1-mini           (needs OPENAI_API_KEY)
    #   Azure:   azure/<deployment>     (needs AZURE_API_KEY, AZURE_API_BASE, AZURE_API_VERSION)
    #   Ollama:  ollama/qwen2.5-coder:7b (free, local)
    llm_model: str = "gpt-4.1-mini"
    llm_timeout_s: int = 60
    llm_reasoning_effort: str | None = None  # e.g. "low" for reasoning models like gpt-5-mini

    # Agent limits
    max_rows: int = 1000          # LIMIT added to every query
    max_retries: int = 2          # self-correction attempts after the first try
    max_question_chars: int = 500
    summary_rows: int = 30        # rows shown to the LLM when writing the answer
    history_turns: int = 3        # previous Q&A turns sent for follow-up questions

    # API
    cors_origins: str = "http://localhost:3000"
    rate_limit_per_minute: int = 20
    # Public-demo protection (so visitors can't drain your OpenAI credit)
    per_ip_daily_limit: int = 0         # questions per visitor per day; 0 = no limit
    daily_question_limit: int = 0       # questions for everyone combined per day; 0 = no limit
    trust_proxy_headers: bool = False   # True behind Render/Vercel/Azure, to read the real visitor IP
    log_db_path: str = str(BACKEND_DIR / "app_logs.db")


@lru_cache
def get_settings() -> Settings:
    return Settings()
