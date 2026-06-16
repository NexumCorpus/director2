"""OpenAI-compatible backends: OpenAI, xAI (Grok), OpenRouter — one class,
three configurations. All speak POST /chat/completions.

OpenRouter default model ids were validated against the live catalogue by the
RDE project (June 2026). Others are sensible defaults — override via
DIRECTOR_MODEL or profile.model if a provider renames.
"""

from __future__ import annotations

import os

from ..errors import ModelProviderError
from .base import LLMBackend, LLMResponse, http_post_json, timed


class OpenAICompatBackend(LLMBackend):
    def __init__(self, name: str, *, base_url: str, key_env: str,
                 default_model: str, cheap_model: str = "",
                 api_key: str | None = None, max_retries: int = 3,
                 extra_headers: dict | None = None):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.cheap_model = cheap_model or default_model
        self.max_retries = max_retries
        self.extra_headers = extra_headers or {}
        self.api_key = api_key or os.environ.get(key_env, "")
        if not self.api_key:
            raise ModelProviderError(f"{key_env} is not set")

    def complete(self, system: str, user: str, *, model: str,
                 temperature: float, max_tokens: int, timeout_s: float,
                 kind: str = "") -> LLMResponse:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            **self.extra_headers,
        }
        data, latency = timed(lambda: http_post_json(
            f"{self.base_url}/chat/completions", headers=headers,
            payload=payload, timeout_s=timeout_s, max_retries=self.max_retries))

        if "error" in data:
            raise ModelProviderError(f"{self.name} error: {data['error']}")
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise ModelProviderError(
                f"{self.name}: malformed response: {str(data)[:300]}") from exc
        usage = data.get("usage") or {}
        return LLMResponse(
            text=text, model=data.get("model", model), backend=self.name,
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            latency_s=latency,
        )


def make_openai(**kw) -> OpenAICompatBackend:
    return OpenAICompatBackend(
        "openai", base_url="https://api.openai.com/v1",
        key_env="OPENAI_API_KEY",
        default_model="gpt-5.4", cheap_model="gpt-5.4-mini", **kw)


def make_xai(**kw) -> OpenAICompatBackend:
    return OpenAICompatBackend(
        "xai", base_url="https://api.x.ai/v1",
        key_env="XAI_API_KEY",
        default_model="grok-4", cheap_model="grok-4", **kw)


def make_openrouter(**kw) -> OpenAICompatBackend:
    return OpenAICompatBackend(
        "openrouter", base_url="https://openrouter.ai/api/v1",
        key_env="OPENROUTER_API_KEY",
        default_model="anthropic/claude-opus-4.8",
        cheap_model="anthropic/claude-haiku-4.5",
        extra_headers={"HTTP-Referer": "https://localhost/director2",
                       "X-Title": "Director 2.0"},
        **kw)
