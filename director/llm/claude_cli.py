"""Claude Code CLI backend — subscription-billed local ``claude -p`` calls.

When metered API credits are unavailable, the locally-installed Claude Code
CLI serves as a backend: headless print mode (``claude -p --output-format
json``) returns the reply plus usage, billed to the user's Claude
subscription instead of an API key.

Safety properties:

* ``ANTHROPIC_API_KEY`` (and Claude-Code nesting markers) are STRIPPED from
  the child environment, so the CLI can never silently fall back to metered
  API billing — the entire point of this backend is subscription quota.
* The user prompt travels over stdin (Windows argv caps near 32k chars;
  Director's project digests can exceed that).
* ``--max-turns 1`` hard-caps each call to a single completion — Director
  wants a text oracle, not a nested agent.

Explicit-only: this backend is never autodetected. Select it with
``DIRECTOR_BACKEND=claude_cli`` in ``.env``; delete that line once the API
key has funds and autodetection resumes.

Knob mapping: ``max_tokens`` -> CLAUDE_CODE_MAX_OUTPUT_TOKENS env var;
``temperature`` has no CLI equivalent and is ignored; ``model`` "" uses the
CLI's configured default model.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time

from ..errors import ModelProviderError, ModelTransientError
from ..logging_setup import get_logger
from .base import LLMBackend, LLMResponse, timed

log = get_logger("llm.claude_cli")

# Strip the whole Anthropic/Claude-Code namespace: API keys (never bill the
# key), and harness markers (a child spawned from inside a Claude Code
# session must authenticate like a fresh terminal, not bind to its parent's
# host-managed auth).
_STRIP_RE = re.compile(r"^(ANTHROPIC_|CLAUDE_?CODE|CLAUDECODE|CLAUDE_AGENT)")

# A subscription/OAuth 401 is a RECOVERABLE auth blip (a token-refresh window or
# a brief auth-service hiccup), NOT a dead credential the way a wrong API key is:
# a genuinely bad token fails the startup ping. So the CLI retries a 401 in
# process with a short backoff, and if it still fails, raises ModelTransientError
# (which the router records but never quarantines) instead of ModelProviderError
# (which the router treats as a permanently dead backend). One blip must not be
# able to kill the only backend. Live finding 2026-06-12: a mid-arc 401 got
# claude_cli quarantined as "dead"; the same token authenticated fine minutes
# later (and again on recheck 2026-06-15 — burst of 6 calls, 6/6 OK).
_AUTH_RETRIES = 2          # extra attempts after the first (3 total)
_AUTH_BACKOFF_S = 2.0      # linear backoff between auth retries: 2s, then 4s


class ClaudeCliBackend(LLMBackend):
    name = "claude_cli"
    # 'sonnet' pinned: the CLI's configured default is a deep-thinking
    # flagship whose 20k-token work orders run 5+ minutes; Sonnet does the
    # same artifact emission 2-3x faster. Override per-run via
    # DIRECTOR_MODEL ('opus', or a full model id).
    default_model = "sonnet"
    cheap_model = "sonnet"          # CLI rejects 'haiku' alias (400)

    def __init__(self, exe: str | None = None):
        self.exe = exe or shutil.which("claude")
        self._rejected_models: set[str] = set()   # models the CLI 400'd this run
        if not self.exe:
            raise ModelProviderError(
                "claude CLI not found on PATH - install Claude Code or "
                "remove DIRECTOR_BACKEND=claude_cli")

    @staticmethod
    def _is_model_rejection(msg: str) -> bool:
        s = msg.lower()
        if "model" not in s:          # an auth/quota error is not about the model
            return False
        return any(t in s for t in ("400", "not_found", "not found", "invalid",
                                    "unknown", "unsupported", "no such"))

    @staticmethod
    def _is_auth_error(msg: str) -> bool:
        """A 401/auth rejection from the CLI. For SUBSCRIPTION auth this is a
        transient blip worth retrying, not a permanent dead-credential the way
        an API-key 401 is — so the backend retries it and raises it as
        TRANSIENT (see _AUTH_RETRIES), keeping the router from quarantining."""
        s = msg.lower()
        return ("401" in s or "unauthorized" in s
                or "authenticat" in s)        # authenticate / authentication

    def _argv(self, model: str, system: str,
              output_format: str = "json") -> list[str]:
        argv = [self.exe]
        if self.exe.lower().endswith((".cmd", ".bat")):
            argv = ["cmd", "/c", self.exe]      # CreateProcess can't run .cmd
        # --tools "" disables ALL built-in tools: the CLI is agentic by
        # default and would spin on tool attempts on Director's prompts.
        # --setting-sources "" loads NO user/project settings: live finding —
        # the child inherited the user's "explanatory" output style and wrote
        # giant insight-block documents instead of contract JSON (reads as a
        # hang). The oracle must run with factory defaults.
        argv += ["-p", "--output-format", output_format,
                 "--max-turns", "1",
                 "--tools", "", "--setting-sources", "",
                 "--no-session-persistence"]
        # stream-json needs --verbose to surface per-message events (empirical:
        # without it the CLI buffers and emits only the terminal result line).
        if output_format == "stream-json":
            argv += ["--verbose"]
        if model:
            argv += ["--model", model]
        if system:
            argv += ["--system-prompt", system]
        return argv

    def complete(self, system: str, user: str, *, model: str,
                 temperature: float, max_tokens: int, timeout_s: float,
                 kind: str = "") -> LLMResponse:
        token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "").strip()
        env = {k: v for k, v in os.environ.items()
               if not _STRIP_RE.match(k)}
        if token:
            # deliberate pass-through: a setup-token credential (from .env)
            # IS subscription auth — the only var allowed across the strip
            env["CLAUDE_CODE_OAUTH_TOKEN"] = token
        # floor 32k: artifact-heavy Director tasks emit 10-20k+ tokens; the
        # CLI HARD-FAILS a call that exceeds this cap (live finding: 7 min
        # of generation discarded), so never let a small profile starve it
        env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = str(max(int(max_tokens),
                                                       32000))
        # small floor for process-spawn headroom, but let DIRECTOR_TIMEOUT_S
        # drive fail-fast — a hardcoded 300s floor silently overrode the
        # operator's 150s cap and let calls hang 5min (live finding 2026-06-13)
        timeout = max(float(timeout_s), 45.0)
        # a model the CLI already rejected this run -> go straight to default
        # (so a misconfigured fast lane costs one probe, not one per call)
        if model and model in self._rejected_models:
            model = self.default_model

        auth_tries = 0           # transient 401s tolerated before giving up
        last_auth = ""
        while True:
            argv = self._argv(model, system)

            def _run():
                return subprocess.run(
                    argv, input=user, capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=timeout,
                    env=env)
            try:
                proc, elapsed = timed(_run)
            except subprocess.TimeoutExpired:
                raise ModelTransientError(
                    f"claude CLI timed out after {timeout:.0f}s")
            except OSError as exc:
                raise ModelProviderError(f"claude CLI failed to launch: {exc}")
            raw = (proc.stdout or proc.stderr or "")
            try:
                data = json.loads(proc.stdout)
            except json.JSONDecodeError:
                data = ({"result": proc.stdout} if proc.returncode == 0
                        else {"is_error": True, "result": raw})
            if not (proc.returncode != 0 or data.get("is_error")):
                break                                       # success
            emsg = str(data)[:400]
            # 1) REJECTED model (400 / not-found): degrade to the default ONCE,
            #    so a misconfigured fast lane can't break a run.
            if (model and model != self.default_model
                    and self._is_model_rejection(emsg)):
                self._rejected_models.add(model)
                log.warning("CLI rejected model %r; falling back to %s",
                            model, self.default_model)
                model = self.default_model
                continue
            # 2) subscription 401: a RECOVERABLE auth blip, not a dead key.
            #    Retry in-process with backoff; if it persists, raise it as
            #    TRANSIENT (never Provider) so the router records the failure but
            #    does NOT quarantine the only backend over one hiccup.
            if self._is_auth_error(emsg):
                last_auth = emsg
                if auth_tries < _AUTH_RETRIES:
                    auth_tries += 1
                    delay = _AUTH_BACKOFF_S * auth_tries
                    log.warning("claude CLI auth blip (401); retry %d/%d "
                                "after %.0fs", auth_tries, _AUTH_RETRIES, delay)
                    time.sleep(delay)
                    continue
                raise ModelTransientError(
                    f"claude CLI auth failed after {_AUTH_RETRIES + 1} attempts "
                    f"(transient 401 - subscription token not accepted by the "
                    f"auth service): {last_auth}")
            # 3) anything else: a non-transient provider rejection.
            if proc.returncode != 0:
                raise ModelProviderError(
                    f"claude CLI exit {proc.returncode}: "
                    f"{(proc.stderr or proc.stdout or '')[:400]}")
            raise ModelProviderError(f"claude CLI error result: {emsg}")
        text = str(data.get("result") or "")
        if not text.strip():
            raise ModelTransientError(
                f"claude CLI returned an empty result "
                f"(subtype={data.get('subtype', '?')})")
        usage = data.get("usage") or {}
        prompt_toks = int(usage.get("input_tokens", 0) or 0) \
            + int(usage.get("cache_read_input_tokens", 0) or 0) \
            + int(usage.get("cache_creation_input_tokens", 0) or 0)
        return LLMResponse(
            text=text, model=model or "cli-default", backend=self.name,
            prompt_tokens=prompt_toks,
            completion_tokens=int(usage.get("output_tokens", 0) or 0),
            latency_s=elapsed,
            meta={"session_id": data.get("session_id", ""),
                  "total_cost_usd": data.get("total_cost_usd", 0),
                  "num_turns": data.get("num_turns", 1)})

    @staticmethod
    def _stream_text_chunks(obj: dict) -> list[str]:
        """Extract assistant TEXT deltas from one stream-json event. Returns []
        for non-text events (system/result/tool/etc.). Truth-in-labeling: only
        type=='text' content is generation; nothing here is reasoning."""
        if not isinstance(obj, dict):
            return []
        if obj.get("type") != "assistant":
            return []
        msg = obj.get("message")
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):
            return []
        out = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                t = block.get("text")
                if isinstance(t, str) and t:
                    out.append(t)
        return out

    def stream(self, system: str, user: str, *, on_event, model: str,
               temperature: float, max_tokens: int, timeout_s: float,
               kind: str = "") -> LLMResponse:
        """Stream the CLI's GENERATION (not reasoning) via
        ``--output-format stream-json --verbose``: spawn with Popen, write the
        prompt over stdin, read stdout line by line, emit one ``text_delta`` per
        assistant text chunk, and return the SAME LLMResponse :meth:`complete`
        returns (the accumulated buffer IS the final text; usage comes from the
        terminal result line). Best-effort observability: on ANY stream failure
        — launch error, no result line, empty/garbled stream — fall back to the
        blocking :meth:`complete`, so the VERIFIED result is always
        authoritative (a stream hiccup can never corrupt it). NEVER emits
        ``thinking_delta`` — the subscription CLI exposes no reasoning."""
        token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "").strip()
        env = {k: v for k, v in os.environ.items() if not _STRIP_RE.match(k)}
        if token:
            env["CLAUDE_CODE_OAUTH_TOKEN"] = token
        env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = str(max(int(max_tokens), 32000))
        timeout = max(float(timeout_s), 45.0)
        if model and model in self._rejected_models:
            model = self.default_model
        argv = self._argv(model, system, output_format="stream-json")

        def _emit(ev: dict) -> None:
            try:
                on_event(ev)
            except Exception:                                 # noqa: BLE001
                pass     # the sink is best-effort; never let it abort the stream

        t0 = time.perf_counter()
        buf: list[str] = []
        result_obj: dict | None = None
        try:
            proc = subprocess.Popen(
                argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, encoding="utf-8",
                errors="replace", env=env)
        except OSError as exc:
            log.warning("claude CLI stream failed to launch (%s); "
                        "falling back to blocking complete()", exc)
            fb = self.complete(system, user, model=model,
                               temperature=temperature, max_tokens=max_tokens,
                               timeout_s=timeout_s, kind=kind)
            _emit({"type": "text_delta", "text": fb.text})
            return fb
        try:
            try:
                proc.stdin.write(user)
                proc.stdin.close()
            except (OSError, ValueError):
                pass
            for line in proc.stdout:
                line = (line or "").strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue                     # tolerate non-JSON noise lines
                if isinstance(obj, dict) and obj.get("type") == "result":
                    result_obj = obj
                    continue
                for chunk in self._stream_text_chunks(obj):
                    buf.append(chunk)
                    _emit({"type": "text_delta", "text": chunk})
            try:
                proc.wait(timeout=timeout)
            except Exception:                                 # noqa: BLE001
                proc.kill()
        except Exception as exc:                              # noqa: BLE001
            log.warning("claude CLI stream read error (%s); falling back to "
                        "blocking complete()", exc)
            try:
                proc.kill()
            except Exception:                                 # noqa: BLE001
                pass
            return self.complete(system, user, model=model,
                                 temperature=temperature, max_tokens=max_tokens,
                                 timeout_s=timeout_s, kind=kind)
        elapsed = time.perf_counter() - t0
        # final text: prefer the authoritative result line; else the buffer.
        final_text = ""
        if result_obj is not None:
            final_text = str(result_obj.get("result") or "")
        if not final_text.strip():
            final_text = "".join(buf)
        if not final_text.strip():
            # nothing usable streamed -> the blocking path is authoritative
            log.warning("claude CLI stream produced no text; falling back to "
                        "blocking complete()")
            return self.complete(system, user, model=model,
                                 temperature=temperature, max_tokens=max_tokens,
                                 timeout_s=timeout_s, kind=kind)
        usage = (result_obj or {}).get("usage") or {}
        prompt_toks = int(usage.get("input_tokens", 0) or 0) \
            + int(usage.get("cache_read_input_tokens", 0) or 0) \
            + int(usage.get("cache_creation_input_tokens", 0) or 0)
        return LLMResponse(
            text=final_text, model=model or "cli-default", backend=self.name,
            prompt_tokens=prompt_toks,
            completion_tokens=int(usage.get("output_tokens", 0) or 0),
            latency_s=elapsed,
            meta={"session_id": (result_obj or {}).get("session_id", ""),
                  "total_cost_usd": (result_obj or {}).get("total_cost_usd", 0),
                  "num_turns": (result_obj or {}).get("num_turns", 1),
                  "streamed": True})
