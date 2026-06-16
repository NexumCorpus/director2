"""LLMRouter — one entry point for every model call in the framework.

Responsibilities:
* backend registry + env autodetection (anthropic > openai > xai > openrouter > mock)
* role→profile mapping (director / builder / adversary / judge / cheap)
* failover across REAL backends only — falling back to mock silently was
  Director 1.0's critical F11 bug; here mock is only used when explicitly
  selected or when no keys exist, and every record carries the backend tag
* structured output: JSON contract appended to the system prompt, reply parsed
  with extract_json, validated with a pydantic schema; on validation failure
  the *error text* is fed back in one retry (F18 lesson: a blind retry of the
  same prompt is a wasted attempt)
* every call (success or failure) is reported to an optional recorder —
  evolve.metrics.PerfLedger plugs in here
"""

from __future__ import annotations

import asyncio
import json
from typing import Awaitable, Callable, Type

from pydantic import BaseModel, ValidationError

from ..config import Config
from ..errors import (ConfigError, ModelError, ModelParseError,
                      ModelProviderError, ModelValidationError)
from ..logging_setup import get_logger
from .base import LLMBackend, LLMResponse, ModelProfile
from .jsonx import extract_json
from .mock import MockBackend

log = get_logger("llm.router")

JSON_CONTRACT = (
    "\n\nOUTPUT CONTRACT: Reply with a single JSON object only - no prose, no "
    "markdown fences, no commentary before or after. The JSON must satisfy the "
    "schema described to you. Use double quotes. Do not include trailing commas."
)


def _build_backend(name: str, cfg: Config) -> LLMBackend:
    if name == "mock":
        return MockBackend()
    if name == "anthropic":
        from .anthropic import AnthropicBackend
        return AnthropicBackend(max_retries=cfg.max_retries)
    if name == "openai":
        from .openai_compat import make_openai
        return make_openai(max_retries=cfg.max_retries)
    if name == "xai":
        from .openai_compat import make_xai
        return make_xai(max_retries=cfg.max_retries)
    if name == "openrouter":
        from .openai_compat import make_openrouter
        return make_openrouter(max_retries=cfg.max_retries)
    if name == "claude_cli":
        # explicit-only (DIRECTOR_BACKEND=claude_cli): subscription-billed
        # local Claude Code CLI; never autodetected
        from .claude_cli import ClaudeCliBackend
        return ClaudeCliBackend()
    raise ConfigError(f"unknown backend '{name}'")


class LLMRouter:
    def __init__(self, cfg: Config, *, backends: dict[str, LLMBackend] | None = None,
                 recorder: Callable[[dict], None] | None = None):
        self.cfg = cfg
        self.recorder = recorder
        self._dead: set[str] = set()   # backends quarantined this session (402/auth)
        if backends is not None:
            self.backends = dict(backends)
            self.primary = next(iter(self.backends))
        else:
            primary = cfg.detect_backend()
            self.backends = {primary: _build_backend(primary, cfg)}
            # register every other real backend with a key as failover
            for name in ("anthropic", "openai", "xai", "openrouter"):
                if name != primary and cfg.api_key(name):
                    try:
                        self.backends[name] = _build_backend(name, cfg)
                    except ModelProviderError:
                        continue
            self.primary = primary
        if self.primary == "mock":
            log.warning("no API keys detected - using MOCK backend "
                        "(deterministic fixtures, NOT a real model)")

    # ------------------------------------------------------------------ info
    @property
    def is_mock(self) -> bool:
        return self.primary == "mock"

    def describe(self) -> list[dict]:
        out = []
        for name, b in self.backends.items():
            out.append({"backend": name, "primary": name == self.primary,
                        "default_model": b.default_model,
                        "cheap_model": b.cheap_model})
        return out

    def profile_for(self, role: str) -> ModelProfile:
        """Role → knobs. Explicit cfg.model wins for the primary roles."""
        base = {
            "director": ModelProfile(
                role="director",
                # pin the director-role temperature when declared (bench
                # reproducibility); else keep the historical 0.2
                temperature=(self.cfg.director_temperature
                             if getattr(self.cfg, "director_temperature", None)
                             is not None else 0.2),
                max_tokens=self.cfg.max_output_tokens,
                timeout_s=self.cfg.request_timeout_s),
            "builder": ModelProfile(role="builder", temperature=0.5,
                                    max_tokens=self.cfg.max_output_tokens,
                                    timeout_s=self.cfg.request_timeout_s),
            "adversary": ModelProfile(role="adversary", temperature=0.7,
                                      max_tokens=4096,
                                      timeout_s=self.cfg.request_timeout_s),
            "judge": ModelProfile(role="judge", temperature=0.0,
                                  max_tokens=4096,
                                  timeout_s=self.cfg.request_timeout_s),
            "cheap": ModelProfile(role="cheap", temperature=0.3,
                                  max_tokens=4096,
                                  timeout_s=self.cfg.request_timeout_s),
        }
        profile = base.get(role, base["director"])
        if self.cfg.model and role in ("director", "builder", "judge"):
            profile = ModelProfile(role=profile.role, model=self.cfg.model,
                                   temperature=profile.temperature,
                                   max_tokens=profile.max_tokens,
                                   timeout_s=profile.timeout_s)
        if self.cfg.cheap_model and role == "cheap":
            profile = ModelProfile(role="cheap", model=self.cfg.cheap_model,
                                   temperature=profile.temperature,
                                   max_tokens=profile.max_tokens,
                                   timeout_s=profile.timeout_s)
        return profile

    # ------------------------------------------------------------------ calls
    def complete(self, system: str, user: str, *, role: str = "director",
                 kind: str = "", profile: ModelProfile | None = None) -> LLMResponse:
        """Free-text completion with failover across real backends."""
        prof = profile or self.profile_for(role)
        # per-kind timeout: heavy single-shot kinds get the long budget; cycle
        # calls keep the fail-fast base (live finding: two-regime timeouts)
        eff_timeout = self.cfg.kind_timeout(kind) if kind else prof.timeout_s
        from ..config import FAST_KINDS
        fast = bool(self.cfg.fast_model) and kind in FAST_KINDS
        errors: list[str] = []
        for name in self._chain():
            backend = self.backends[name]
            # low-stakes kinds (command_packet, …) take the fast model when one
            # is configured; deliverables + verification keep the primary model
            model = self.cfg.fast_model if fast else backend.resolve_model(prof)
            try:
                resp = backend.complete(
                    system, user, model=model, temperature=prof.temperature,
                    max_tokens=prof.max_tokens, timeout_s=eff_timeout,
                    kind=kind)
                self._record(kind=kind, role=role, resp=resp, ok=True)
                return resp
            except ModelError as exc:
                errors.append(f"{name}: {type(exc).__name__}: {exc}")
                self._record(kind=kind, role=role, ok=False,
                             backend=name, model=model,
                             error=f"{type(exc).__name__}: {exc}")
                self._quarantine_if_dead(name, exc)
                log.warning("backend %s failed for kind=%s: %s", name, kind, exc)
        raise ModelError("all backends failed: " + " | ".join(errors))

    def structured(self, system: str, user: str, schema: Type[BaseModel], *,
                   role: str = "director", kind: str = "",
                   profile: ModelProfile | None = None) -> BaseModel:
        """Completion coerced into ``schema``. One feedback retry on
        parse/validation failure (the error is appended to the user prompt so
        the model has a corrective signal)."""
        sys_prompt = system + JSON_CONTRACT + \
            "\n\nJSON SCHEMA (informal):\n" + _schema_sketch(schema)
        attempt_user = user
        last_exc: Exception | None = None
        for attempt in range(self.cfg.validation_retries + 1):
            resp = self.complete(sys_prompt, attempt_user, role=role, kind=kind,
                                 profile=profile)
            try:
                return self._validate_reply(resp, schema, kind)
            except (ModelParseError, ModelValidationError) as exc:
                last_exc = exc
            if attempt < self.cfg.validation_retries:
                attempt_user = self._retry_user(user, last_exc)
                log.info("structured retry for kind=%s after: %s", kind, last_exc)
        assert last_exc is not None
        raise last_exc

    # ------------------------------------------------------------------- async
    async def acomplete(self, system: str, user: str, *, role: str = "director",
                        kind: str = "",
                        profile: ModelProfile | None = None) -> LLMResponse:
        """Async free-text completion — same failover/timeout/recording as
        :meth:`complete`, awaiting each backend's :meth:`acomplete`."""
        prof = profile or self.profile_for(role)
        eff_timeout = self.cfg.kind_timeout(kind) if kind else prof.timeout_s
        from ..config import FAST_KINDS
        fast = bool(self.cfg.fast_model) and kind in FAST_KINDS
        errors: list[str] = []
        for name in self._chain():
            backend = self.backends[name]
            model = self.cfg.fast_model if fast else backend.resolve_model(prof)
            try:
                resp = await backend.acomplete(
                    system, user, model=model, temperature=prof.temperature,
                    max_tokens=prof.max_tokens, timeout_s=eff_timeout, kind=kind)
                self._record(kind=kind, role=role, resp=resp, ok=True)
                return resp
            except ModelError as exc:
                errors.append(f"{name}: {type(exc).__name__}: {exc}")
                self._record(kind=kind, role=role, ok=False, backend=name,
                             model=model, error=f"{type(exc).__name__}: {exc}")
                self._quarantine_if_dead(name, exc)
                log.warning("backend %s failed (async) kind=%s: %s",
                            name, kind, exc)
        raise ModelError("all backends failed: " + " | ".join(errors))

    async def astructured(self, system: str, user: str, schema: Type[BaseModel],
                          *, role: str = "director", kind: str = "",
                          profile: ModelProfile | None = None) -> BaseModel:
        """Async structured output — same one-feedback-retry contract as
        :meth:`structured` (shares :meth:`_validate_reply`, so the two can never
        drift)."""
        sys_prompt = system + JSON_CONTRACT + \
            "\n\nJSON SCHEMA (informal):\n" + _schema_sketch(schema)
        attempt_user = user
        last_exc: Exception | None = None
        for attempt in range(self.cfg.validation_retries + 1):
            resp = await self.acomplete(sys_prompt, attempt_user, role=role,
                                        kind=kind, profile=profile)
            try:
                return self._validate_reply(resp, schema, kind)
            except (ModelParseError, ModelValidationError) as exc:
                last_exc = exc
            if attempt < self.cfg.validation_retries:
                attempt_user = self._retry_user(user, last_exc)
                log.info("astructured retry for kind=%s after: %s", kind,
                         last_exc)
        assert last_exc is not None
        raise last_exc

    async def agather(self, thunks: list[Callable[[], Awaitable]], *,
                      limit: int | None = None) -> list:
        """Run async call-thunks concurrently, bounded by a semaphore (default
        cfg.max_parallel_agents). Returns results in input order; a thunk that
        raises comes back as its Exception (return_exceptions) so one failure
        never cancels the batch — filter with isinstance before use."""
        sem = asyncio.Semaphore(limit or self.cfg.max_parallel_agents)

        async def _run(thunk):
            async with sem:
                return await thunk()
        return await asyncio.gather(*(_run(t) for t in thunks),
                                    return_exceptions=True)

    # ------------------------------------------------------------------ private
    def _validate_reply(self, resp: LLMResponse, schema: Type[BaseModel],
                        kind: str) -> BaseModel:
        """Parse + validate a transport reply into ``schema``, attaching the raw
        response. Raises ModelParseError / ModelValidationError. Shared by sync
        and async paths so their coercion can never diverge."""
        try:
            data = extract_json(resp.text)
        except ValueError as exc:
            raise ModelParseError(f"{kind or 'call'}: {exc}; reply started: "
                                  f"{resp.text[:200]!r}")
        try:
            obj = schema.model_validate(data)
        except ValidationError as exc:
            raise ModelValidationError(
                f"{kind or 'call'}: schema validation failed: {exc}")
        # attach transport response without tripping pydantic's __setattr__
        object.__setattr__(obj, "_llm_response", resp)
        return obj

    @staticmethod
    def _retry_user(user: str, last_exc: Exception | None) -> str:
        return (user + "\n\nYOUR PREVIOUS REPLY WAS REJECTED.\n"
                f"Validator error:\n{last_exc}\n"
                "Return ONLY corrected JSON that satisfies the schema.")
    def _chain(self) -> list[str]:
        """Primary first, then other real backends. Mock participates only when
        it IS the primary (no-keys mode) — never as a silent fallback. Backends
        quarantined this session (permanent 402/auth failure) are skipped so a
        dead key isn't hammered on every call (live finding: a credits-exhausted
        OpenRouter fallback was retried on every cycle)."""
        chain = [self.primary]
        chain += [n for n in self.backends if n != self.primary and n != "mock"]
        live = [n for n in chain if n not in self._dead]
        return live or chain        # if all are quarantined, try anyway

    @staticmethod
    def _is_dead_error(exc: Exception) -> bool:
        """A permanent backend failure (no credits / bad auth) — quarantine it,
        don't retry it. Transient timeouts/rate-limits are NOT dead."""
        if not isinstance(exc, ModelProviderError):
            return False
        s = str(exc).lower()
        return any(t in s for t in ("402", "401", "403", "insufficient credit",
                                    "no credit", "quota exceeded"))

    def _quarantine_if_dead(self, name: str, exc: Exception) -> None:
        if name != "mock" and self._is_dead_error(exc) and name not in self._dead:
            self._dead.add(name)
            log.warning("quarantining backend '%s' for the session "
                        "(permanent failure, will not retry): %s", name, exc)

    def _record(self, *, kind: str, role: str, ok: bool,
                resp: LLMResponse | None = None, backend: str = "",
                model: str = "", error: str = "") -> None:
        if not self.recorder:
            return
        try:
            self.recorder({
                "kind": kind, "role": role, "ok": ok,
                "backend": resp.backend if resp else backend,
                "model": resp.model if resp else model,
                "latency_s": round(resp.latency_s, 4) if resp else None,
                "prompt_tokens": resp.prompt_tokens if resp else 0,
                "completion_tokens": resp.completion_tokens if resp else 0,
                "error": error,
            })
        except Exception:                                     # noqa: BLE001
            log.exception("perf recorder failed (non-fatal)")


def _schema_sketch(schema: Type[BaseModel]) -> str:
    """Human/LLM-readable sketch of a pydantic schema (full JSON schema is
    noisy; models follow a compact sketch better)."""
    try:
        js = schema.model_json_schema()
    except Exception:                                          # noqa: BLE001
        return schema.__name__
    return json.dumps(_strip_schema(js), indent=1)[:4000]


def _strip_schema(node):
    if isinstance(node, dict):
        keep = {k: v for k, v in node.items()
                if k in ("properties", "items", "required", "type", "enum",
                         "description", "$defs", "$ref", "anyOf", "default")}
        return {k: _strip_schema(v) for k, v in keep.items()}
    if isinstance(node, list):
        return [_strip_schema(v) for v in node]
    return node
