"""LLM backend contract + shared transport plumbing.

A backend does exactly one thing: turn (system, user, knobs) into text + usage.
Routing, structured-output validation, retries-with-feedback, and performance
recording all live in :mod:`director.llm.router` so every backend gets them
for free.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import httpx

from ..errors import (ModelProviderError, ModelRateLimitError,
                      ModelTransientError)


@dataclass(frozen=True)
class ModelProfile:
    """Per-call knobs. ``role`` names an orchestration role (director, builder,
    adversary, judge, cheap); the router maps roles to models per backend."""
    role: str = "director"
    model: str = ""                 # explicit model id overrides role mapping
    temperature: float = 0.3
    max_tokens: int = 4096
    timeout_s: float = 120.0


@dataclass
class LLMResponse:
    text: str
    model: str = ""
    backend: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_s: float = 0.0
    meta: dict = field(default_factory=dict)


class LLMBackend(ABC):
    """One provider. Implementations: anthropic, openai-compatible, mock."""

    name: str = "abstract"
    default_model: str = ""
    cheap_model: str = ""

    @abstractmethod
    def complete(self, system: str, user: str, *, model: str,
                 temperature: float, max_tokens: int, timeout_s: float,
                 kind: str = "") -> LLMResponse:
        """Single-turn completion. ``kind`` is a routing hint (e.g.
        'initial_plan') that real backends ignore; the mock keys fixtures on it."""

    async def acomplete(self, system: str, user: str, *, model: str,
                        temperature: float, max_tokens: int, timeout_s: float,
                        kind: str = "") -> LLMResponse:
        """Async completion. The default runs the sync :meth:`complete` in a
        worker thread, so EVERY backend is usable from async code without
        rewriting its (sync httpx) transport. This is honest concurrency — real
        threads, not a fake await — and a backend with a native async client may
        override this for true non-blocking IO."""
        import asyncio
        return await asyncio.to_thread(
            self.complete, system, user, model=model, temperature=temperature,
            max_tokens=max_tokens, timeout_s=timeout_s, kind=kind)

    def stream(self, system: str, user: str, *, on_event, model: str,
               temperature: float, max_tokens: int, timeout_s: float,
               kind: str = "") -> LLMResponse:
        """Stream a completion, calling ``on_event(dict)`` per delta, and return
        the SAME LLMResponse :meth:`complete` would. The default is the honest
        non-streaming path: run the blocking call, then emit the whole result as
        ONE ``text_delta`` — so every backend is a usable streaming source and
        the router gets a deterministic side-channel even on backends with no
        native token stream (mock, anthropic, openai_compat). A backend with a
        real token stream (claude_cli) OVERRIDES this. Truth-in-labeling: the
        default NEVER emits ``thinking_delta`` — there is no reasoning here."""
        resp = self.complete(system, user, model=model, temperature=temperature,
                             max_tokens=max_tokens, timeout_s=timeout_s,
                             kind=kind)
        try:
            on_event({"type": "text_delta", "text": resp.text})
        except Exception:                                     # noqa: BLE001
            pass     # the sink is best-effort observability; never corrupt resp
        return resp

    def resolve_model(self, profile: ModelProfile) -> str:
        if profile.model:
            return profile.model
        if profile.role == "cheap" and self.cheap_model:
            return self.cheap_model
        return self.default_model


def http_post_json(url: str, *, headers: dict, payload: dict,
                   timeout_s: float, max_retries: int = 3) -> dict:
    """POST with exponential backoff on transient failures (1s, 2s, 4s).

    Raises ModelRateLimitError / ModelTransientError / ModelProviderError —
    callers never see raw httpx exceptions.
    """
    last_err: Exception | None = None
    for attempt in range(max(1, max_retries)):
        try:
            resp = httpx.post(url, headers=headers, json=payload,
                              timeout=timeout_s)
            if resp.status_code == 429:
                last_err = ModelRateLimitError(f"429 from {url}: {resp.text[:300]}")
            elif resp.status_code >= 500:
                last_err = ModelTransientError(
                    f"HTTP {resp.status_code} from {url}: {resp.text[:300]}")
            elif resp.status_code >= 400:
                raise ModelProviderError(
                    f"HTTP {resp.status_code} from {url}: {resp.text[:500]}")
            else:
                return resp.json()
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_err = ModelTransientError(f"transport error: {exc}")
        except ValueError as exc:  # resp.json() failed
            last_err = ModelTransientError(f"non-JSON response: {exc}")
        if attempt < max_retries - 1:
            time.sleep(2 ** attempt)
    if isinstance(last_err, (ModelRateLimitError, ModelTransientError)):
        raise last_err
    raise ModelTransientError(f"gave up after {max_retries} attempts: {last_err}")


def timed(fn):
    """Run fn(), return (result, elapsed_seconds)."""
    t0 = time.perf_counter()
    result = fn()
    return result, time.perf_counter() - t0
