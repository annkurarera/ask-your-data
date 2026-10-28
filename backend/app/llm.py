"""LLM client. Every model call goes through LiteLLM, so switching between
OpenAI, Azure (Foundry), Anthropic, Gemini or local Ollama is a .env change."""
import json
import re
import time
from dataclasses import dataclass, field
from typing import Protocol

from .config import Settings, get_settings


@dataclass
class LLMResponse:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0

    def add(self, r: LLMResponse) -> None:
        self.calls += 1
        self.input_tokens += r.input_tokens
        self.output_tokens += r.output_tokens
        self.cost_usd += r.cost_usd


class LLMClient(Protocol):
    def complete(self, messages: list[dict], json_mode: bool = False) -> LLMResponse: ...


@dataclass
class LiteLLMClient:
    settings: Settings = field(default_factory=get_settings)

    def complete(self, messages: list[dict], json_mode: bool = False) -> LLMResponse:
        import litellm

        litellm.drop_params = True  # ignore params a model doesn't support (e.g. temperature on reasoning models)
        kwargs: dict = {
            "model": self.settings.llm_model,
            "messages": messages,
            "temperature": 0,
            "timeout": self.settings.llm_timeout_s,
            "num_retries": 2,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if self.settings.llm_reasoning_effort:
            kwargs["reasoning_effort"] = self.settings.llm_reasoning_effort

        start = time.perf_counter()
        resp = litellm.completion(**kwargs)
        latency = int((time.perf_counter() - start) * 1000)

        usage = getattr(resp, "usage", None)
        try:
            cost = float(litellm.completion_cost(completion_response=resp) or 0.0)
        except Exception:  # unknown/local models have no price table
            cost = 0.0
        return LLMResponse(
            text=resp.choices[0].message.content or "",
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
            cost_usd=cost,
            latency_ms=latency,
        )


def parse_json_reply(text: str) -> dict:
    """Parse the model's JSON reply, tolerating code fences or extra prose."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    # Last resort: a bare ```sql block
    sql = re.search(r"```sql\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if sql:
        return {"action": "sql", "sql": sql.group(1).strip(), "reasoning": ""}
    raise ValueError("Model reply was not valid JSON")
