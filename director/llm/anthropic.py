"""Anthropic (Claude) backend — native Messages API via httpx.

Defaults to the latest, most capable Claude for director-grade reasoning and a
Haiku-class model for cheap calls. Override with DIRECTOR_MODEL /
DIRECTOR_CHEAP_MODEL or per-profile.
"""

from __future__ import annotations

import os

from ..errors import ModelProviderError
from .base import LLMBackend, LLMResponse, http_post_json, timed

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


class AnthropicBackend(LLMBackend):
    name = "anthropic"
    default_model = "claude-fable-5"
    cheap_model = "claude-haiku-4-5-20251001"

    def __init__(self, api_key: str | None = None, *,
                 base_url: str = API_URL, max_retries: int = 3):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.base_url = base_url
        self.max_retries = max_retries
        if not self.api_key:
            raise ModelProviderError("ANTHROPIC_API_KEY is not set")

    def complete(self, system: str, user: str, *, model: str,
                 temperature: float, max_tokens: int, timeout_s: float,
                 kind: str = "") -> LLMResponse:
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        }
        data, latency = timed(lambda: http_post_json(
            self.base_url, headers=headers, payload=payload,
            timeout_s=timeout_s, max_retries=self.max_retries))

        if data.get("type") == "error":
            raise ModelProviderError(f"anthropic error: {data.get('error')}")
        parts = data.get("content") or []
        text = "".join(p.get("text", "") for p in parts
                       if isinstance(p, dict) and p.get("type") == "text")
        usage = data.get("usage") or {}
        return LLMResponse(
            text=text, model=data.get("model", model), backend=self.name,
            prompt_tokens=int(usage.get("input_tokens", 0)),
            completion_tokens=int(usage.get("output_tokens", 0)),
            latency_s=latency,
            meta={"stop_reason": data.get("stop_reason")},
        )
