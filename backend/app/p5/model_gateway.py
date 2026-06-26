from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Model gateway: a thin, provider-agnostic wrapper around chat completions.
#
# Design constraints (see plan.md P5):
# - OpenAI-compatible request shape so we are not locked to one vendor; switching
#   to Bailian/Qwen/etc. later is a config change (base_url/model/api_key).
# - A `mock` provider so the system runs with no API key and stays deterministic.
# - Standard library only for now (urllib); swapping in the openai SDK later is
#   a localized change inside DeepSeekProvider.
# - The gateway never decides business facts; callers must still validate output
#   (e.g. draft_safety) before using it.

PROJECT_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_FALLBACK_MODEL = "deepseek-v4-pro"


@dataclass(frozen=True)
class ModelConfig:
    provider: str = "mock"  # "mock" | "deepseek"
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    fallback_model: str | None = DEFAULT_FALLBACK_MODEL
    api_key: str | None = None
    max_tokens: int = 1024  # must leave room for reasoning_content on v4 models
    temperature: float = 0.2
    timeout: int = 60
    max_repair_attempts: int = 1  # extra model calls to fix a draft that fails safety


@dataclass
class ModelResponse:
    ok: bool
    text: str  # final answer only (content); reasoning is kept separate
    model: str
    provider: str
    latency_ms: int
    usage: dict[str, Any] = field(default_factory=dict)
    reasoning: str = ""
    used_fallback: bool = False
    error: str | None = None


class MockProvider:
    name = "mock"

    def __init__(self, config: ModelConfig) -> None:
        self.config = config

    def complete(self, messages, *, model=None, max_tokens=None, temperature=None) -> ModelResponse:
        # Deterministic and offline: echo the last user message. For a "polish"
        # call (instructions in system, draft in user) this returns the draft
        # unchanged, which exercises the full plumbing + safety gate without a key.
        start = time.monotonic()
        text = last_user_message(messages)
        latency_ms = int((time.monotonic() - start) * 1000)
        return ModelResponse(
            ok=True,
            text=text,
            model="mock",
            provider=self.name,
            latency_ms=latency_ms,
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        )


class DeepSeekProvider:
    name = "deepseek"

    def __init__(self, config: ModelConfig) -> None:
        self.config = config

    def complete(self, messages, *, model=None, max_tokens=None, temperature=None) -> ModelResponse:
        model = model or self.config.model
        body = {
            "model": model,
            "messages": messages,
            "stream": False,
            "max_tokens": max_tokens or self.config.max_tokens,
            "temperature": self.config.temperature if temperature is None else temperature,
        }
        start = time.monotonic()
        try:
            payload = self._post(f"{self.config.base_url}/chat/completions", body)
        except Exception as error:  # network / HTTP / decode
            return ModelResponse(
                ok=False,
                text="",
                model=model,
                provider=self.name,
                latency_ms=int((time.monotonic() - start) * 1000),
                error=str(error),
            )

        latency_ms = int((time.monotonic() - start) * 1000)
        choices = payload.get("choices") or []
        message = choices[0].get("message", {}) if choices else {}
        # v4 models are reasoning models: the answer is in `content`, the chain of
        # thought in `reasoning_content`. Business logic only ever uses `content`.
        text = (message.get("content") or "").strip()
        return ModelResponse(
            ok=bool(text),
            text=text,
            model=payload.get("model", model),
            provider=self.name,
            latency_ms=latency_ms,
            usage=payload.get("usage") or {},
            reasoning=message.get("reasoning_content") or "",
            error=None if text else "model returned empty content",
        )

    def _post(self, url: str, body: dict) -> dict:
        data = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(url, data=data, method="POST")
        request.add_header("Authorization", f"Bearer {self.config.api_key}")
        request.add_header("Content-Type", "application/json")
        request.add_header("Accept", "application/json")
        with urllib.request.urlopen(request, timeout=self.config.timeout) as response:
            return json.loads(response.read().decode("utf-8"))


class ModelGateway:
    def __init__(self, provider: Any, config: ModelConfig) -> None:
        self.provider = provider
        self.config = config

    def complete(self, messages, *, max_tokens=None, temperature=None) -> ModelResponse:
        response = self.provider.complete(
            messages, model=self.config.model, max_tokens=max_tokens, temperature=temperature
        )
        if response.ok:
            return response
        # Fallback to a stronger model on failure (real providers only).
        if (
            self.provider.name != "mock"
            and self.config.fallback_model
            and self.config.fallback_model != self.config.model
        ):
            fallback = self.provider.complete(
                messages,
                model=self.config.fallback_model,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            fallback.used_fallback = True
            return fallback
        return response


def build_gateway(config: ModelConfig | None = None) -> ModelGateway:
    config = config or load_model_config()
    if config.provider == "mock":
        return ModelGateway(MockProvider(config), config)
    if config.provider == "deepseek":
        if not config.api_key:
            raise ValueError(
                "LLM_PROVIDER=deepseek requires an API key (set LLM_API_KEY or DEEPSEEK_API_KEY)."
            )
        return ModelGateway(DeepSeekProvider(config), config)
    raise ValueError(f"Unknown LLM_PROVIDER: {config.provider!r} (expected 'mock' or 'deepseek').")


def load_model_config() -> ModelConfig:
    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
    fallback = os.environ.get("LLM_FALLBACK_MODEL", DEFAULT_FALLBACK_MODEL).strip()
    return ModelConfig(
        provider=os.environ.get("LLM_PROVIDER", "mock").strip().lower(),
        base_url=os.environ.get("LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
        model=os.environ.get("LLM_MODEL", DEFAULT_MODEL).strip(),
        fallback_model=fallback or None,
        api_key=api_key.strip() if api_key else None,
        max_tokens=int(os.environ.get("LLM_MAX_TOKENS", "1024")),
        temperature=float(os.environ.get("LLM_TEMPERATURE", "0.2")),
        timeout=int(os.environ.get("LLM_TIMEOUT", "60")),
        max_repair_attempts=int(os.environ.get("LLM_MAX_REPAIR_ATTEMPTS", "1")),
    )


def last_user_message(messages: list[dict[str, str]]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            return str(message.get("content") or "")
    return ""


def load_dotenv(path: Path) -> None:
    # Minimal .env loader (no dependency). Existing env vars take precedence.
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = _parse_env_value(value.strip())
        if key and key not in os.environ:
            os.environ[key] = value


def _parse_env_value(value: str) -> str:
    # Quoted values are taken verbatim (so a '#' inside is preserved); unquoted
    # values drop an inline comment that follows whitespace, e.g. `1024  # note`.
    if value[:1] in ('"', "'"):
        quote = value[0]
        end = value.find(quote, 1)
        return value[1:end] if end != -1 else value[1:]
    for index, char in enumerate(value):
        if char == "#" and index > 0 and value[index - 1] in " \t":
            return value[:index].strip()
    return value
