"""Verify a DeepSeek API key works, before wiring it into P5.

Standard library only — run with:

    uv run python scripts/check_deepseek_api.py

The key is read from the DEEPSEEK_API_KEY environment variable, or from a
`.env` file in the repo root (which is git-ignored). The key is never printed.

What it does:
  1. GET /user/balance   -> confirms auth and shows remaining balance
  2. POST /chat/completions with a tiny prompt -> confirms inference works,
     prints the reply and token usage.

Config via env (all optional except the key):
  DEEPSEEK_API_KEY   required
  DEEPSEEK_BASE_URL  default https://api.deepseek.com
  DEEPSEEK_MODEL     default deepseek-v4-flash

Docs: https://api-docs.deepseek.com/zh-cn/
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"
TIMEOUT_SECONDS = 30

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")

    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY is not set.")
        print("Set it for this shell:")
        print('  export DEEPSEEK_API_KEY="sk-..."')
        print("or put it in a .env file at the repo root (it is git-ignored):")
        print("  DEEPSEEK_API_KEY=sk-...")
        return 2

    base_url = os.environ.get("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    model = os.environ.get("DEEPSEEK_MODEL", DEFAULT_MODEL).strip()

    print(f"base_url: {base_url}")
    print(f"model:    {model}")
    print(f"api_key:  {mask(api_key)}")
    print()

    balance_ok = check_balance(base_url, api_key)
    print()
    chat_ok = check_chat(base_url, api_key, model)

    print()
    if chat_ok:
        print("RESULT: OK — the API key works.")
        return 0
    # Balance alone passing still means auth works, but inference is what P5 needs.
    print("RESULT: FAILED — see the error above.")
    return 1


def check_balance(base_url: str, api_key: str) -> bool:
    print("[1/2] GET /user/balance ...")
    try:
        status, payload = request_json(
            "GET", f"{base_url}/user/balance", api_key, body=None
        )
    except ApiError as error:
        # Balance is a nice-to-have; don't fail the whole check on it.
        print(f"  skipped: {error}")
        return False

    is_available = payload.get("is_available")
    print(f"  is_available: {is_available}")
    for info in payload.get("balance_infos", []):
        currency = info.get("currency")
        total = info.get("total_balance")
        print(f"  balance: {total} {currency}")
    return bool(is_available)


def check_chat(base_url: str, api_key: str, model: str) -> bool:
    print("[2/2] POST /chat/completions ...")
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a connectivity test."},
            {"role": "user", "content": "Reply with the single word: OK"},
        ],
        "stream": False,
        # deepseek-v4-* are reasoning models: max_tokens INCLUDES the thinking
        # chain, so a tiny cap leaves no room for the final answer. Keep headroom.
        "max_tokens": 256,
        "temperature": 0,
    }
    try:
        status, payload = request_json(
            "POST", f"{base_url}/chat/completions", api_key, body=body
        )
    except ApiError as error:
        print(f"  {error}")
        return False

    choices = payload.get("choices") or []
    message = choices[0].get("message", {}) if choices else {}
    content = (message.get("content") or "").strip()
    reasoning = message.get("reasoning_content") or ""
    finish_reason = choices[0].get("finish_reason") if choices else None
    usage = payload.get("usage") or {}
    reasoning_tokens = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")

    print(f"  http status:   {status}")
    print(f"  model:         {payload.get('model')}")
    print(f"  finish_reason: {finish_reason}")
    if reasoning:
        print(f"  reasoning:     {len(reasoning)} chars (thinking model — kept out of content)")
    print(f"  reply:         {content!r}")
    print(
        "  tokens:        "
        f"prompt={usage.get('prompt_tokens')} "
        f"completion={usage.get('completion_tokens')} "
        f"reasoning={reasoning_tokens} "
        f"total={usage.get('total_tokens')}"
    )
    if not content and finish_reason == "length":
        print("  WARN: truncated by max_tokens before a final answer; raise max_tokens.")
    return bool(content)


class ApiError(Exception):
    pass


def request_json(method: str, url: str, api_key: str, body: dict | None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Authorization", f"Bearer {api_key}")
    request.add_header("Accept", "application/json")
    if data is not None:
        request.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = read_error_detail(error)
        raise ApiError(f"HTTP {error.code} {error.reason}: {detail}{http_hint(error.code)}") from error
    except urllib.error.URLError as error:
        raise ApiError(
            f"network error: {error.reason}. "
            "Check connectivity to api.deepseek.com (proxy/VPN if needed)."
        ) from error


def read_error_detail(error: urllib.error.HTTPError) -> str:
    try:
        payload = json.loads(error.read().decode("utf-8"))
    except Exception:
        return "<no JSON body>"
    message = payload.get("error", {})
    if isinstance(message, dict):
        return message.get("message", json.dumps(payload, ensure_ascii=False))
    return str(message)


def http_hint(code: int) -> str:
    hints = {
        401: "  -> invalid API key.",
        402: "  -> insufficient balance; top up your DeepSeek account.",
        404: "  -> wrong path or model id; check DEEPSEEK_BASE_URL / DEEPSEEK_MODEL.",
        422: "  -> invalid request params (e.g. unknown model id).",
        429: "  -> rate limited; retry later.",
    }
    return "\n" + hints[code] if code in hints else ""


def mask(secret: str) -> str:
    if len(secret) <= 8:
        return "****"
    return f"{secret[:4]}...{secret[-4:]} (len {len(secret)})"


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
    # Quoted values verbatim; unquoted values drop an inline comment after
    # whitespace, e.g. `1024  # note`.
    if value[:1] in ('"', "'"):
        quote = value[0]
        end = value.find(quote, 1)
        return value[1:end] if end != -1 else value[1:]
    for index, char in enumerate(value):
        if char == "#" and index > 0 and value[index - 1] in " \t":
            return value[:index].strip()
    return value


if __name__ == "__main__":
    sys.exit(main())
