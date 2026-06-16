# Director 2.0 — Live Generation Streaming + Watchable Live Runs (implementation plan)

- **Date:** 2026-06-16
- **Spec:** `E:\director2\docs\superpowers\specs\2026-06-16-director2-live-generation-streaming-design.md` (APPROVED — architecture decided; do not redesign)
- **Project:** Director 2.0 (`E:\director2`), branch `live-streaming`
- **Baseline:** 414 tests passing on `live-streaming` at plan-authoring time.

## Goal

Stream the model's **generation** (the `_plan()` call on the `claude_cli` backend, plan-first) to the web dashboard over SSE, honestly labeled as *generation* (NOT reasoning); persist the raw generation on the run record; and patch the live-test workflow so live runs are selectable and repeatable without leaking billing into the default test suite. Everything new is gated by `cfg.stream_generation` (default `False`); with the gate off the framework is byte-identical and the full pre-existing suite stays green.

## Architecture

A backend-agnostic **event protocol** (`{"type":"text_delta","text":...}`; a `"thinking_delta"` type is *reserved* and never emitted by `claude_cli`) carried by an `on_event` **callback sink** from the backend up through the router, the Director plan surface, and into a per-project **thread-safe queue** on the dashboard `BridgeHub`, drained to the browser over **SSE** (`GET /api/project/{id}/stream`), and rendered in a dedicated, honestly-labeled "Live generation" pane in `ui.py`.

```
ClaudeCliBackend.stream(system, user, *, on_event)        # Popen --output-format stream-json --verbose
        emits on_event({"type":"text_delta","text": chunk})
   -> LLMRouter.stream_structured(..., on_event)          # accumulate text, parse FINAL -> schema (identical to structured())
   -> Director._plan(sink wired) <- new_project(sink)      # gated; capture raw_generation
   -> BridgeHub stream queue (thread-safe, per-project, cursor)
   -> GET /api/project/{id}/stream  (text/event-stream)    # SSE drain + terminal sentinel
   -> ui.py EventSource -> "Live generation" pane          # honestly labeled
```

**Non-negotiable invariants (asserted in tests, stated in every task):**

1. **OFF byte-identical.** All new behavior is gated by `cfg.stream_generation` (default `False`). Gate off → no streaming code runs → the 414-test pre-existing suite stays green. *If a pre-existing test changes, that is a leak past the gate — fix the gate, never the test.*
2. **Non-breaking core.** `LLMBackend.complete()` / `LLMRouter.structured()` are **NOT modified**. Streaming adds **parallel** methods: `ClaudeCliBackend.stream()`, `LLMRouter.stream_structured()`. The final parse/return is **identical** to non-streaming.
3. **Stream failure cannot corrupt a result.** Streaming is best-effort observability. On any stream/parse error, fall back to blocking `complete()` / `structured()` so the verified result is always authoritative.
4. **Truth-in-labeling.** The channel is "generation"/"output", NEVER "thinking". `text_delta` now; `thinking_delta` reserved and never emitted by `claude_cli`. UI header reads "model output as it's written — not hidden reasoning".
5. **Explicit-only live, no accidental billing.** `claude_cli` is never autodetected. Live is selected by `--backend` / `Config(backend=...)` / `DIRECTOR_BACKEND`. Tests stay mock unless `DIRECTOR_LIVE_BACKEND` opts in (a `tests/conftest.py` change).

## Tech Stack

- Pure-Python 3.11+, stdlib only (`subprocess.Popen`, `http.server`, `queue`, `threading`, `json`). No new dependencies.
- pytest. Run **everything** as `python -m pytest` from `E:\director2`.
- Existing libs already in the tree: `pydantic`, `click`, `httpx` (transport only — not touched here).
- Git on branch `live-streaming`. Commit style mirrors existing log (e.g. `feat(stream): ...`, `test(stream): ...`, `fix(stream): ...`).

## REQUIRED SUB-SKILL: subagent-driven-development

Execute this plan with the **superpowers:subagent-driven-development** skill. Each task below is a self-contained unit a fresh subagent (ZERO prior context) can complete: it has exact file paths, the exact current-code anchor to splice against, complete replacement code (no placeholders), the exact pytest command, the expected FAIL-then-PASS, and a commit step. Run tasks in order; do not start a task until the previous task's suite is green.

---

## File structure table

| File | Responsibility | Create / Modify |
|---|---|---|
| `director/config.py` | `stream_generation: bool = False` gate + `DIRECTOR_STREAM_GENERATION` env wiring | Modify |
| `director/cli.py` | `--backend` option on `new` and `dashboard` commands → `Config(backend=...)` | Modify |
| `tests/conftest.py` | `DIRECTOR_LIVE_BACKEND` opt-in (do NOT blank provider vars when set) | Modify |
| `director/llm/base.py` | `LLMBackend.stream(...)` default = call `complete()` + emit one `text_delta` (non-streaming backends inherit it) | Modify |
| `director/llm/claude_cli.py` | `ClaudeCliBackend.stream(...)` — `Popen --output-format stream-json --verbose` line reader, emits `text_delta`, returns identical `LLMResponse`; falls back to `complete()` on any stream error | Modify |
| `director/llm/router.py` | `LLMRouter.stream_structured(...)` — mirrors `structured()`, threads `on_event`, parses FINAL accumulated text; mock/no-stream fallback emits one whole-result `text_delta` | Modify |
| `director/agents/base.py` | `AgentResult.raw_generation: str = ""` | Modify |
| `director/core/types.py` | `AgentRun.raw_generation: str = ""` (round-trips via existing encode/decode) | Modify |
| `director/agents/runner.py` | capture `resp.text` into `result.raw_generation` (currently discarded) | Modify |
| `director/core/director.py` | `_record_run` copies `raw_generation`; `_plan(objective, *, on_event=None)` uses `stream_structured` when gated+sink; `new_project(name, objective, *, on_event=None)` threads the sink | Modify |
| `director/dashboard/server.py` | `BridgeHub` per-project stream queue + cursor + sink factory; `GET /api/project/{id}/stream` SSE route | Modify |
| `director/dashboard/ui.py` | `EventSource` + honestly-labeled "Live generation" pane + dormant `thinking_delta` branch | Modify |
| `tests/test_stream_config.py` | Phase 1 tests | Create |
| `tests/test_stream_backend.py` | Phase 2 backend + router tests | Create |
| `tests/test_stream_capture.py` | Phase 2 `raw_generation` capture/round-trip tests | Create |
| `tests/test_stream_plan.py` | Phase 3 plan-surface streaming tests | Create |
| `tests/test_stream_sse.py` | Phase 4 dashboard SSE + UI tests | Create |

---

# Phase 1 — Workflow patch + gate

**Outcome:** `stream_generation` gate exists (default `False`); `--backend` makes a live run selectable robustly; `tests/conftest.py` honors `DIRECTOR_LIVE_BACKEND`. `python -m pytest` GREEN.

## Task 1.1 — Add the `stream_generation` gate to `Config`

**Files:**
- `E:\director2\director\config.py` (modify)
- `E:\director2\tests\test_stream_config.py` (create)

### Step 1 — Write the failing test

Create `E:\director2\tests\test_stream_config.py`:

```python
"""Live-generation-streaming: config gate + workflow patch (Phase 1).
All offline; no backend is ever reached."""

import os

from director.config import Config


# ---------------------------------------------------------------- the gate
def test_stream_generation_defaults_false():
    # OFF byte-identical: the gate must default False so no streaming code runs
    assert Config().stream_generation is False


def test_stream_generation_env_truthy(monkeypatch):
    monkeypatch.setenv("DIRECTOR_STREAM_GENERATION", "1")
    assert Config.from_env().stream_generation is True


def test_stream_generation_env_falsey(monkeypatch):
    monkeypatch.setenv("DIRECTOR_STREAM_GENERATION", "0")
    assert Config.from_env().stream_generation is False


def test_stream_generation_env_absent_is_false(monkeypatch):
    monkeypatch.delenv("DIRECTOR_STREAM_GENERATION", raising=False)
    assert Config.from_env().stream_generation is False
```

### Step 2 — Run it (expected FAIL)

```
python -m pytest tests/test_stream_config.py -q
```

Expected: FAIL — `AttributeError: 'Config' object has no attribute 'stream_generation'` (and `from_env` does not set it).

### Step 3 — Implement

In `E:\director2\director\config.py`, add the gate field. Anchor (the `--- LLM transport ---` block ends with `temperature: float = 0.3`):

```python
    max_output_tokens: int = 8192      # live finding: 4096 truncated real Opus JSON
    temperature: float = 0.3
```

Replace with:

```python
    max_output_tokens: int = 8192      # live finding: 4096 truncated real Opus JSON
    temperature: float = 0.3
    # --- live generation streaming ------------------------------------------
    # DEFAULT FALSE: OFF byte-identical. With it off, no streaming code runs and
    # the pre-existing suite stays green; only when ON does _plan stream its
    # generation to the dashboard sink. Honest label: GENERATION, not reasoning.
    stream_generation: bool = False
```

Then wire the env var in `Config.from_env`. Anchor (inside the `cfg = cls(...)` call):

```python
            loop_iterations=_env_int("DIRECTOR_LOOP_ITERATIONS", 6),
            builder_fanout=_env_int("DIRECTOR_BUILDER_FANOUT", 1),
            log_level=os.environ.get("DIRECTOR_LOG_LEVEL", "INFO").strip().upper() or "INFO",
        )
```

Replace with:

```python
            loop_iterations=_env_int("DIRECTOR_LOOP_ITERATIONS", 6),
            builder_fanout=_env_int("DIRECTOR_BUILDER_FANOUT", 1),
            log_level=os.environ.get("DIRECTOR_LOG_LEVEL", "INFO").strip().upper() or "INFO",
            stream_generation=os.environ.get(
                "DIRECTOR_STREAM_GENERATION", "").strip().lower() in _TRUTHY,
        )
```

(`_TRUTHY = {"1", "true", "yes", "on"}` already exists at module top.)

### Step 4 — Run it (expected PASS)

```
python -m pytest tests/test_stream_config.py -q
```

Expected: 4 passed.

### Step 5 — Full suite (gate must not leak)

```
python -m pytest -q
```

Expected: all previously-passing tests still pass (414 + the 4 new = 418), no failures.

### Step 6 — Commit

```
git add director/config.py tests/test_stream_config.py
git commit -m "feat(stream): stream_generation gate (default False, OFF byte-identical)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 1.2 — `--backend` CLI flag → `Config(backend=...)`

The root cause (spec §5): `detect_backend()` is explicit-only for `claude_cli`; a non-interactive run without `DIRECTOR_BACKEND` reaching the process degrades to `mock`. A `--backend` flag lets a live run be selected directly, robust against a blanked environment. The `Services` object builds `Config.from_env()` once; we let `new` and `dashboard` override `cfg.backend` before services are built.

**Files:**
- `E:\director2\director\cli.py` (modify)
- `E:\director2\tests\test_stream_config.py` (append)

### Step 1 — Write the failing test

Append to `E:\director2\tests\test_stream_config.py`:

```python
# ------------------------------------------------------- --backend selection
def test_config_backend_makes_detect_return_it():
    # the robust live-selection path: a config-level backend wins, even with a
    # blanked env (claude_cli stays explicit-only; never autodetected)
    assert Config(backend="claude_cli").detect_backend() == "claude_cli"
    assert Config(backend="").detect_backend() == "mock"


def test_cli_new_accepts_backend_flag():
    # the `new` command exposes --backend so a live run is selectable directly
    from click.testing import CliRunner

    from director.cli import main
    res = CliRunner().invoke(main, ["new", "--help"])
    assert res.exit_code == 0
    assert "--backend" in res.output


def test_cli_dashboard_accepts_backend_flag():
    from click.testing import CliRunner

    from director.cli import main
    res = CliRunner().invoke(main, ["dashboard", "--help"])
    assert res.exit_code == 0
    assert "--backend" in res.output
```

### Step 2 — Run it (expected FAIL)

```
python -m pytest tests/test_stream_config.py -q
```

Expected: `test_config_backend_makes_detect_return_it` PASSES already (existing behavior), the two `--help` tests FAIL (`--backend` not in output).

### Step 3 — Implement

In `E:\director2\director\cli.py`, add a helper to override the backend on the lazily-built services, then add the flag to `new` and `dashboard`.

Anchor — the `_services()` helper:

```python
def _services() -> Services:
    ctx = click.get_current_context()
    if not isinstance(ctx.obj, Services):
        ctx.obj = Services()
    return ctx.obj
```

Replace with:

```python
def _services(backend: str = "") -> Services:
    ctx = click.get_current_context()
    if not isinstance(ctx.obj, Services):
        # explicit --backend wins before services are built, so a blanked
        # environment can't silently defeat a deliberate live selection
        # (claude_cli stays explicit-only; never autodetected). Set it in the
        # environment too so any nested Config.from_env() agrees.
        if backend:
            import os as _os
            _os.environ["DIRECTOR_BACKEND"] = backend
        ctx.obj = Services()
        if backend:
            ctx.obj.cfg.backend = backend
    return ctx.obj
```

Anchor — the `new` command:

```python
@main.command()
@click.argument("name")
@click.option("--objective", "-o", required=True, help="What to achieve.")
def new(name: str, objective: str) -> None:
    """Create a project: charter, modules, task graph, first command packet."""
    svc = _services()
```

Replace with:

```python
@main.command()
@click.argument("name")
@click.option("--objective", "-o", required=True, help="What to achieve.")
@click.option("--backend", default="",
              help="Explicit backend (e.g. claude_cli) — overrides autodetect.")
def new(name: str, objective: str, backend: str) -> None:
    """Create a project: charter, modules, task graph, first command packet."""
    svc = _services(backend)
```

Anchor — the `dashboard` command:

```python
@main.command()
@click.option("--port", default=8765, help="Localhost port (default 8765).")
@click.option("--open", "open_browser", is_flag=True,
              help="Open the bridge in your browser.")
@click.option("--seed-demo", is_flag=True,
              help="(Re)create the zero-quota DEMO campaign first.")
def dashboard(port: int, open_browser: bool, seed_demo: bool) -> None:
    """Launch the Command Bridge: live operations view + command-packet
    decisions at http://127.0.0.1:<port>/ (same JSON API agents can drive)."""
    from .dashboard import run_dashboard
    if seed_demo:
        from .dashboard.demo import seed_demo as _seed
        svc = _services()
        pid = _seed(svc.store)
        click.secho(f"seeded DEMO campaign {pid}", fg="green")
```

Replace with:

```python
@main.command()
@click.option("--port", default=8765, help="Localhost port (default 8765).")
@click.option("--open", "open_browser", is_flag=True,
              help="Open the bridge in your browser.")
@click.option("--seed-demo", is_flag=True,
              help="(Re)create the zero-quota DEMO campaign first.")
@click.option("--backend", default="",
              help="Explicit backend (e.g. claude_cli) — overrides autodetect.")
def dashboard(port: int, open_browser: bool, seed_demo: bool,
              backend: str) -> None:
    """Launch the Command Bridge: live operations view + command-packet
    decisions at http://127.0.0.1:<port>/ (same JSON API agents can drive)."""
    from .dashboard import run_dashboard
    if backend:
        import os as _os
        _os.environ["DIRECTOR_BACKEND"] = backend
    if seed_demo:
        from .dashboard.demo import seed_demo as _seed
        svc = _services(backend)
        pid = _seed(svc.store)
        click.secho(f"seeded DEMO campaign {pid}", fg="green")
```

> Note: `run_dashboard()` builds its own `BridgeHub()` → `Config.from_env()`, so setting `os.environ["DIRECTOR_BACKEND"]` before it runs is what makes the dashboard go live. The `--seed-demo` path also benefits from the same env set.

### Step 4 — Run it (expected PASS)

```
python -m pytest tests/test_stream_config.py -q
```

Expected: all pass.

### Step 5 — Full suite

```
python -m pytest -q
```

Expected: still green (no pre-existing test changed).

### Step 6 — Commit

```
git add director/cli.py tests/test_stream_config.py
git commit -m "feat(stream): --backend flag on new/dashboard for robust live selection

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 1.3 — `DIRECTOR_LIVE_BACKEND` opt-in in `tests/conftest.py`

The autouse `_no_real_provider_keys` fixture blanks `DIRECTOR_BACKEND` and provider keys so tests can never bill. We add a documented escape hatch: when `DIRECTOR_LIVE_BACKEND` is set, the fixture does NOT blank for that run, so pytest can go live deliberately. Default stays safe (mock, no billing).

**Files:**
- `E:\director2\tests\conftest.py` (modify)
- `E:\director2\tests\test_stream_config.py` (append)

### Step 1 — Write the failing test

Append to `E:\director2\tests\test_stream_config.py`:

```python
# ------------------------------------------------- conftest live opt-in
def test_conftest_blanks_by_default(monkeypatch):
    # the autouse fixture ran for THIS test (no opt-in) -> backend env blanked
    import os
    assert os.environ.get("DIRECTOR_BACKEND", "") == ""


def test_live_opt_in_helper_present():
    # the opt-in env var name is documented in conftest source (the seam exists)
    from pathlib import Path
    src = Path(__file__).resolve().parent / "conftest.py"
    text = src.read_text(encoding="utf-8")
    assert "DIRECTOR_LIVE_BACKEND" in text
```

### Step 2 — Run it (expected FAIL)

```
python -m pytest tests/test_stream_config.py -q
```

Expected: `test_live_opt_in_helper_present` FAILS (`DIRECTOR_LIVE_BACKEND` not in conftest yet); `test_conftest_blanks_by_default` PASSES.

### Step 3 — Implement

In `E:\director2\tests\conftest.py`, replace the autouse fixture body. Anchor:

```python
@pytest.fixture(autouse=True)
def _no_real_provider_keys(monkeypatch):
    """Tests must NEVER reach a real backend. Vars are BLANKED (not deleted):
    load_dotenv only fills variables absent from the environment, so an
    empty string also blocks re-injection from a developer's .env file —
    the leak that let two CLI tests bill real calls on 2026-06-12, and that
    later let DIRECTOR_BACKEND=claude_cli spawn real CLI processes."""
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "XAI_API_KEY",
                "OPENROUTER_API_KEY", "DIRECTOR_BACKEND", "DIRECTOR_MODEL",
                "DIRECTOR_CHEAP_MODEL"):
        monkeypatch.setenv(var, "")
```

Replace with:

```python
@pytest.fixture(autouse=True)
def _no_real_provider_keys(monkeypatch):
    """Tests must NEVER reach a real backend. Vars are BLANKED (not deleted):
    load_dotenv only fills variables absent from the environment, so an
    empty string also blocks re-injection from a developer's .env file —
    the leak that let two CLI tests bill real calls on 2026-06-12, and that
    later let DIRECTOR_BACKEND=claude_cli spawn real CLI processes.

    DELIBERATE LIVE OPT-IN: when DIRECTOR_LIVE_BACKEND is set, the suite is
    being run intentionally against a real backend (e.g. claude_cli) — do NOT
    blank, and seed DIRECTOR_BACKEND from it so detect_backend() goes live.
    Default (var unset) stays safe: mock, no billing."""
    import os
    live = os.environ.get("DIRECTOR_LIVE_BACKEND", "").strip()
    if live:
        monkeypatch.setenv("DIRECTOR_BACKEND", live)
        return
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "XAI_API_KEY",
                "OPENROUTER_API_KEY", "DIRECTOR_BACKEND", "DIRECTOR_MODEL",
                "DIRECTOR_CHEAP_MODEL"):
        monkeypatch.setenv(var, "")
```

### Step 4 — Run it (expected PASS)

```
python -m pytest tests/test_stream_config.py -q
```

Expected: all pass. (`DIRECTOR_LIVE_BACKEND` is not set in CI, so the default-blank branch runs and `test_conftest_blanks_by_default` stays green.)

### Step 5 — Full suite

```
python -m pytest -q
```

Expected: still green. (No real backend reachable because `DIRECTOR_LIVE_BACKEND` is unset.)

### Step 6 — Commit

```
git add tests/conftest.py tests/test_stream_config.py
git commit -m "test(stream): DIRECTOR_LIVE_BACKEND opt-in (default stays mock, no billing)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

# Phase 2 — Backend stream + router stream_structured + raw_generation capture

**Outcome:** `LLMBackend.stream()` default + `ClaudeCliBackend.stream()` (Popen line reader) + `LLMRouter.stream_structured()` (mirror of `structured()` with sink + fallback) + `raw_generation` captured/persisted/round-tripped. `complete()`/`structured()` untouched. `python -m pytest` GREEN.

## Task 2.1 — `LLMBackend.stream()` default (emit one delta from `complete()`)

A default `stream()` on the base means every backend (mock, anthropic, openai_compat) is usable as a streaming source without rewriting it: it calls `complete()` and emits the whole result as one `text_delta`. `ClaudeCliBackend` (Task 2.2) overrides it with a real token stream. `complete()` is **not** modified.

**Files:**
- `E:\director2\director\llm\base.py` (modify)
- `E:\director2\tests\test_stream_backend.py` (create)

### Step 1 — Write the failing test

Create `E:\director2\tests\test_stream_backend.py`:

```python
"""Live-generation-streaming backend + router (Phase 2). All offline:
mock backend + a canned stream-json fixture; no real CLI is ever spawned."""

import json
import subprocess

import pytest

from director.config import Config
from director.llm import claude_cli
from director.llm.base import LLMResponse
from director.llm.claude_cli import ClaudeCliBackend
from director.llm.mock import MockBackend


# ------------------------------------------------ base default stream()
def test_base_stream_default_emits_one_delta_and_returns_response():
    b = MockBackend()
    events = []
    resp = b.stream("SYS", "USER", on_event=events.append, model="",
                    temperature=0.3, max_tokens=64, timeout_s=30, kind="")
    assert isinstance(resp, LLMResponse)
    # exactly one text_delta carrying the whole completion text
    deltas = [e for e in events if e.get("type") == "text_delta"]
    assert len(deltas) == 1
    assert deltas[0]["text"] == resp.text
    # the non-streaming backend NEVER emits thinking_delta
    assert not any(e.get("type") == "thinking_delta" for e in events)


def test_base_stream_returns_identical_text_to_complete():
    b = MockBackend()
    kw = dict(model="", temperature=0.3, max_tokens=64, timeout_s=30,
              kind="initial_plan")
    r_complete = b.complete("SYS", "objective: x", **kw)
    r_stream = b.stream("SYS", "objective: x", on_event=lambda e: None, **kw)
    assert r_stream.text == r_complete.text
    assert r_stream.backend == r_complete.backend == "mock"
```

### Step 2 — Run it (expected FAIL)

```
python -m pytest tests/test_stream_backend.py -q
```

Expected: FAIL — `AttributeError: 'MockBackend' object has no attribute 'stream'`.

### Step 3 — Implement

In `E:\director2\director\llm\base.py`, add a `stream()` method to `LLMBackend` (do NOT touch `complete`). Anchor — the `acomplete` default method (ends just before `resolve_model`):

```python
        import asyncio
        return await asyncio.to_thread(
            self.complete, system, user, model=model, temperature=temperature,
            max_tokens=max_tokens, timeout_s=timeout_s, kind=kind)

    def resolve_model(self, profile: ModelProfile) -> str:
```

Replace with:

```python
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
```

### Step 4 — Run it (expected PASS)

```
python -m pytest tests/test_stream_backend.py -q
```

Expected: 2 passed.

### Step 5 — Full suite

```
python -m pytest -q
```

Expected: green (no pre-existing test exercises `stream`; `complete` is unchanged).

### Step 6 — Commit

```
git add director/llm/base.py tests/test_stream_backend.py
git commit -m "feat(stream): LLMBackend.stream() default — one text_delta from complete()

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2.2 — `ClaudeCliBackend.stream()` — Popen stream-json line reader

Build argv like `complete()` but with `--output-format stream-json --verbose`; spawn with `Popen`, write `user` to stdin, read stdout line by line, `json.loads` each line, emit a `text_delta` per assistant text chunk, accumulate into a buffer, and on the terminal `result` event return an `LLMResponse` whose `.text` is the accumulated buffer (identical shape to `complete()`). On ANY stream failure (launch error, no usable text), fall back to `self.complete(...)` so the verified result is always authoritative. The `claude_cli` backend NEVER emits `thinking_delta`.

The real `stream-json --verbose` event shapes (from the empirical probe documented in the spec §1): a `{"type":"system",...}` init line; `{"type":"assistant","message":{"content":[{"type":"text","text":"..."}]}}` lines carrying generation; and a terminal `{"type":"result","subtype":"success","result":"<full text>","usage":{...},"session_id":...,"total_cost_usd":...,"num_turns":...}` line. We tolerate non-JSON lines and missing fields.

**Files:**
- `E:\director2\director\llm\claude_cli.py` (modify)
- `E:\director2\tests\test_stream_backend.py` (append)

### Step 1 — Write the failing test

Append to `E:\director2\tests\test_stream_backend.py`:

```python
# ----------------------------------------- claude_cli stream-json line reader
class _FakeStdout:
    """A line-iterable stdout that also supports read()."""
    def __init__(self, lines):
        self._lines = list(lines)

    def __iter__(self):
        return iter(self._lines)

    def read(self):
        return "".join(self._lines)


class _FakeProc:
    def __init__(self, lines, returncode=0):
        self.stdin = _FakeStdin()
        self.stdout = _FakeStdout(lines)
        self.returncode = returncode

    def wait(self, timeout=None):
        return self.returncode

    def poll(self):
        return self.returncode

    def kill(self):
        pass


class _FakeStdin:
    def write(self, data):
        pass

    def close(self):
        pass


def _stream_lines(chunks, full=None, in_toks=10, out_toks=5):
    full = full if full is not None else "".join(chunks)
    lines = [json.dumps({"type": "system", "subtype": "init",
                         "session_id": "s1"}) + "\n"]
    for ch in chunks:
        lines.append(json.dumps({
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": ch}]}}) + "\n")
    lines.append(json.dumps({
        "type": "result", "subtype": "success", "is_error": False,
        "result": full, "session_id": "s1", "total_cost_usd": 0, "num_turns": 1,
        "usage": {"input_tokens": in_toks, "output_tokens": out_toks,
                  "cache_read_input_tokens": 0,
                  "cache_creation_input_tokens": 0}}) + "\n")
    return lines


def test_claude_stream_emits_delta_per_chunk_and_concats(monkeypatch):
    chunks = ['{"charter":', ' {"objective":', ' "x"}}']
    proc = _FakeProc(_stream_lines(chunks))
    monkeypatch.setattr(claude_cli.subprocess, "Popen", lambda *a, **k: proc)
    b = ClaudeCliBackend(exe=r"C:\fake\claude.exe")
    events = []
    resp = b.stream("SYS", "USER", on_event=events.append, model="",
                    temperature=0.3, max_tokens=64, timeout_s=60, kind="")
    deltas = [e["text"] for e in events if e.get("type") == "text_delta"]
    assert deltas == chunks                     # one text_delta per assistant chunk
    assert resp.text == "".join(chunks)         # final == concatenation
    assert resp.backend == "claude_cli"
    assert resp.prompt_tokens == 10 and resp.completion_tokens == 5
    # NEVER reasoning on the subscription CLI
    assert not any(e.get("type") == "thinking_delta" for e in events)


def test_claude_stream_uses_stream_json_argv(monkeypatch):
    seen = {}

    def fake_popen(argv, **kw):
        seen["argv"] = argv
        return _FakeProc(_stream_lines(["ok"]))

    monkeypatch.setattr(claude_cli.subprocess, "Popen", fake_popen)
    b = ClaudeCliBackend(exe=r"C:\fake\claude.exe")
    b.stream("S", "U", on_event=lambda e: None, model="", temperature=0,
             max_tokens=64, timeout_s=60, kind="")
    argv = seen["argv"]
    assert argv[argv.index("--output-format") + 1] == "stream-json"
    assert "--verbose" in argv
    assert argv[argv.index("--max-turns") + 1] == "1"
    assert argv[argv.index("--tools") + 1] == ""


def test_claude_stream_tolerates_garbage_lines(monkeypatch):
    lines = ["not json\n"] + _stream_lines(["A", "B"])
    monkeypatch.setattr(claude_cli.subprocess, "Popen",
                        lambda *a, **k: _FakeProc(lines))
    b = ClaudeCliBackend(exe=r"C:\fake\claude.exe")
    events = []
    resp = b.stream("S", "U", on_event=events.append, model="", temperature=0,
                    max_tokens=64, timeout_s=60, kind="")
    assert resp.text == "AB"
    assert [e["text"] for e in events if e.get("type") == "text_delta"] == ["A", "B"]


def test_claude_stream_falls_back_to_complete_on_launch_error(monkeypatch):
    def boom(*a, **k):
        raise OSError("cannot spawn")

    monkeypatch.setattr(claude_cli.subprocess, "Popen", boom)
    # complete() path is exercised via subprocess.run -> mock it to a real reply
    def fake_run(argv, **kw):
        return subprocess.CompletedProcess(
            argv, 0,
            stdout=json.dumps({"type": "result", "subtype": "success",
                               "is_error": False, "result": "FALLBACK",
                               "usage": {"input_tokens": 1, "output_tokens": 1}}),
            stderr="")

    monkeypatch.setattr(claude_cli.subprocess, "run", fake_run)
    b = ClaudeCliBackend(exe=r"C:\fake\claude.exe")
    events = []
    resp = b.stream("S", "U", on_event=events.append, model="", temperature=0,
                    max_tokens=64, timeout_s=60, kind="")
    # the verified result is authoritative even when the stream can't be established
    assert resp.text == "FALLBACK"
    # the base-default-style single delta is emitted from the fallback text
    assert [e["text"] for e in events if e.get("type") == "text_delta"] == ["FALLBACK"]
```

### Step 2 — Run it (expected FAIL)

```
python -m pytest tests/test_stream_backend.py -q
```

Expected: the four `test_claude_stream_*` FAIL — `AttributeError: 'ClaudeCliBackend' object has no attribute 'stream'` (the base default isn't used because we'll override it). The Task-2.1 tests still pass.

### Step 3 — Implement

In `E:\director2\director\llm\claude_cli.py`:

First, refactor `_argv` so the output format is a parameter (so `stream()` and `complete()` share one argv builder without `complete()` changing behavior). Anchor:

```python
    def _argv(self, model: str, system: str) -> list[str]:
        argv = [self.exe]
        if self.exe.lower().endswith((".cmd", ".bat")):
            argv = ["cmd", "/c", self.exe]      # CreateProcess can't run .cmd
        # --tools "" disables ALL built-in tools: the CLI is agentic by
        # default and would spin on tool attempts on Director's prompts.
        # --setting-sources "" loads NO user/project settings: live finding —
        # the child inherited the user's "explanatory" output style and wrote
        # giant insight-block documents instead of contract JSON (reads as a
        # hang). The oracle must run with factory defaults.
        argv += ["-p", "--output-format", "json", "--max-turns", "1",
                 "--tools", "", "--setting-sources", "",
                 "--no-session-persistence"]
        if model:
            argv += ["--model", model]
        if system:
            argv += ["--system-prompt", system]
        return argv
```

Replace with:

```python
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
```

> `complete()` calls `self._argv(model, system)` with the default `output_format="json"`, so its argv is byte-identical to before — the existing `test_complete_contract` (which asserts `--output-format json`) stays green.

Now add the `stream()` method. Insert it immediately AFTER the `complete()` method (i.e. after the final `return LLMResponse(...)` block at the end of `complete`, which is the last method in the class). Anchor — the end of `complete`:

```python
        return LLMResponse(
            text=text, model=model or "cli-default", backend=self.name,
            prompt_tokens=prompt_toks,
            completion_tokens=int(usage.get("output_tokens", 0) or 0),
            latency_s=elapsed,
            meta={"session_id": data.get("session_id", ""),
                  "total_cost_usd": data.get("total_cost_usd", 0),
                  "num_turns": data.get("num_turns", 1)})
```

Replace with (appends the new method after `complete`):

```python
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
            return self.complete(system, user, model=model,
                                 temperature=temperature, max_tokens=max_tokens,
                                 timeout_s=timeout_s, kind=kind)
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
```

### Step 4 — Run it (expected PASS)

```
python -m pytest tests/test_stream_backend.py -q
```

Expected: all pass.

### Step 5 — Full suite (existing claude_cli tests must stay green)

```
python -m pytest tests/test_claude_cli.py -q
python -m pytest -q
```

Expected: `test_complete_contract` (asserts `--output-format json` and the unchanged argv) stays green because `complete()` calls `_argv` with the default `output_format="json"`. Whole suite green.

### Step 6 — Commit

```
git add director/llm/claude_cli.py tests/test_stream_backend.py
git commit -m "feat(stream): ClaudeCliBackend.stream() — stream-json line reader, falls back to complete()

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2.3 — `LLMRouter.stream_structured()` — mirror `structured()` with a sink + fallback

`stream_structured()` mirrors `structured()` exactly (same backend selection, same system-prompt assembly with `JSON_CONTRACT` + `_schema_sketch`, same one-feedback-retry, same `_validate_reply` so coercion can never drift), differing only by threading `on_event` to `backend.stream(...)`. If `on_event` is `None` it routes straight to `structured()` (zero overhead when no sink). On any streaming error it falls back to the blocking `complete()`/validate path so the validated result is always authoritative.

**Files:**
- `E:\director2\director\llm\router.py` (modify)
- `E:\director2\tests\test_stream_backend.py` (append)

### Step 1 — Write the failing test

Append to `E:\director2\tests\test_stream_backend.py`:

First, add these imports/helper to the TOP of `tests/test_stream_backend.py` if not already present (the file already imports `Config`, `MockBackend`). Then append the three tests below.

```python
# ---------------------------------------------------- router stream_structured
from director.core.director import PlanOut  # noqa: E402
from director.llm.router import LLMRouter  # noqa: E402


def _router_mock():
    return LLMRouter(Config(), backends={"mock": MockBackend()})


def test_stream_structured_mock_emits_one_delta_and_matches_structured():
    r = _router_mock()
    events = []
    a = r.stream_structured("SYS", "objective: build x", PlanOut,
                            on_event=events.append, role="director",
                            kind="initial_plan")
    b = r.structured("SYS", "objective: build x", PlanOut, role="director",
                     kind="initial_plan")
    # identical validated schema (same fixture) — only the side-channel differs
    assert a.model_dump() == b.model_dump()
    deltas = [e for e in events if e.get("type") == "text_delta"]
    assert len(deltas) == 1 and deltas[0]["text"]   # mock -> one whole-result delta
    assert not any(e.get("type") == "thinking_delta" for e in events)


def test_stream_structured_none_sink_routes_to_structured():
    r = _router_mock()
    out = r.stream_structured("SYS", "objective: y", PlanOut, on_event=None,
                              role="director", kind="initial_plan")
    ref = r.structured("SYS", "objective: y", PlanOut, role="director",
                       kind="initial_plan")
    assert out.model_dump() == ref.model_dump()


def test_stream_structured_returns_validated_schema_type():
    r = _router_mock()
    out = r.stream_structured("SYS", "objective: z", PlanOut,
                              on_event=lambda e: None, role="director",
                              kind="initial_plan")
    assert isinstance(out, PlanOut) and out.tasks
```

### Step 2 — Run it (expected FAIL)

```
python -m pytest tests/test_stream_backend.py -q
```

Expected: the three `test_stream_structured_*` FAIL — `AttributeError: 'LLMRouter' object has no attribute 'stream_structured'`.

### Step 3 — Implement

In `E:\director2\director\llm\router.py`, add `stream_structured` and a small `_stream_complete` helper. Place them immediately AFTER `structured()` (before the `# ----- async` section). Anchor — the end of `structured`:

```python
            if attempt < self.cfg.validation_retries:
                attempt_user = self._retry_user(user, last_exc)
                log.info("structured retry for kind=%s after: %s", kind, last_exc)
        assert last_exc is not None
        raise last_exc

    # ------------------------------------------------------------------- async
```

Replace with:

```python
            if attempt < self.cfg.validation_retries:
                attempt_user = self._retry_user(user, last_exc)
                log.info("structured retry for kind=%s after: %s", kind, last_exc)
        assert last_exc is not None
        raise last_exc

    def _stream_complete(self, system: str, user: str, *, role: str, kind: str,
                         profile: ModelProfile | None, on_event
                         ) -> LLMResponse:
        """Free-text completion that threads ``on_event`` to the backend's
        :meth:`stream`, with the SAME failover/timeout/recording as
        :meth:`complete`. Best-effort: if a backend's stream raises, record the
        failure and fail over exactly like complete() would — the caller's
        retry/validate path stays authoritative."""
        prof = profile or self.profile_for(role)
        eff_timeout = self.cfg.kind_timeout(kind) if kind else prof.timeout_s
        from ..config import FAST_KINDS
        fast = bool(self.cfg.fast_model) and kind in FAST_KINDS
        errors: list[str] = []
        for name in self._chain():
            backend = self.backends[name]
            model = self.cfg.fast_model if fast else backend.resolve_model(prof)
            try:
                resp = backend.stream(
                    system, user, on_event=on_event, model=model,
                    temperature=prof.temperature, max_tokens=prof.max_tokens,
                    timeout_s=eff_timeout, kind=kind)
                self._record(kind=kind, role=role, resp=resp, ok=True)
                return resp
            except ModelError as exc:
                errors.append(f"{name}: {type(exc).__name__}: {exc}")
                self._record(kind=kind, role=role, ok=False, backend=name,
                             model=model, error=f"{type(exc).__name__}: {exc}")
                self._quarantine_if_dead(name, exc)
                log.warning("backend %s stream failed for kind=%s: %s",
                            name, kind, exc)
        raise ModelError("all backends failed (stream): " + " | ".join(errors))

    def stream_structured(self, system: str, user: str, schema: Type[BaseModel],
                          *, on_event=None, role: str = "director",
                          kind: str = "",
                          profile: ModelProfile | None = None) -> BaseModel:
        """Streaming twin of :meth:`structured`. IDENTICAL backend selection,
        prompt assembly, one-feedback-retry, and final parse/validate (shares
        :meth:`_validate_reply`, so coercion can NEVER diverge from structured()).
        The ONLY difference is a side-channel of generation deltas: ``on_event``
        is threaded to the backend's :meth:`stream`. With ``on_event=None`` (no
        sink) it delegates straight to :meth:`structured` — zero overhead, byte-
        identical. Truth-in-labeling: the deltas are GENERATION, never reasoning;
        the validated result is exactly what structured() would return."""
        if on_event is None:
            return self.structured(system, user, schema, role=role, kind=kind,
                                   profile=profile)
        sys_prompt = system + JSON_CONTRACT + \
            "\n\nJSON SCHEMA (informal):\n" + _schema_sketch(schema)
        attempt_user = user
        last_exc: Exception | None = None
        for attempt in range(self.cfg.validation_retries + 1):
            resp = self._stream_complete(sys_prompt, attempt_user, role=role,
                                         kind=kind, profile=profile,
                                         on_event=on_event)
            try:
                return self._validate_reply(resp, schema, kind)
            except (ModelParseError, ModelValidationError) as exc:
                last_exc = exc
            if attempt < self.cfg.validation_retries:
                attempt_user = self._retry_user(user, last_exc)
                log.info("stream_structured retry for kind=%s after: %s",
                         kind, last_exc)
        assert last_exc is not None
        raise last_exc

    # ------------------------------------------------------------------- async
```

### Step 4 — Run it (expected PASS)

```
python -m pytest tests/test_stream_backend.py -q
```

Expected: all pass.

### Step 5 — Full suite

```
python -m pytest -q
```

Expected: green. (`structured()` untouched; `stream_structured` is additive.)

### Step 6 — Commit

```
git add director/llm/router.py tests/test_stream_backend.py
git commit -m "feat(stream): LLMRouter.stream_structured() — mirrors structured() with on_event sink

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2.4 — Capture `raw_generation` on `AgentResult` / `AgentRun` and round-trip it

Add `raw_generation: str = ""` to `AgentResult` (`agents/base.py`) and `AgentRun` (`core/types.py`); capture `resp.text` in `SubAgentRunner.run()` (currently fetched at `runner.py:52` then discarded); copy it through `Director._record_run` so it persists and round-trips via the existing generic `encode`/`decode` (zero migration).

**Files:**
- `E:\director2\director\agents\base.py` (modify)
- `E:\director2\director\core\types.py` (modify)
- `E:\director2\director\agents\runner.py` (modify)
- `E:\director2\director\core\director.py` (modify — `_record_run`)
- `E:\director2\tests\test_stream_capture.py` (create)

### Step 1 — Write the failing test

Create `E:\director2\tests\test_stream_capture.py`:

```python
"""raw_generation capture + persistence + round-trip (Phase 2). Offline mock."""

from director.agents.base import AgentResult
from director.agents.runner import SubAgentRunner
from director.core.director import Director
from director.core.state import ProjectStore
from director.core.types import AgentRun, decode, encode
from director.llm.mock import MockBackend
from director.llm.router import LLMRouter
from director.verify import make_default_registry


def test_agentresult_has_raw_generation_field():
    r = AgentResult(spec_id="s")
    assert r.raw_generation == ""


def test_agentrun_raw_generation_round_trips():
    run = AgentRun(task_id="t", role="code", raw_generation='{"summary":"hi"}')
    back = decode(AgentRun, encode(run))
    assert back.raw_generation == '{"summary":"hi"}'


def test_runner_captures_raw_generation(cfg):
    router = LLMRouter(cfg, backends={"mock": MockBackend()})
    registry = make_default_registry()
    runner = SubAgentRunner(cfg, router, registry)
    from director.agents.base import AgentSpec
    res = runner.run(AgentSpec(role="research", objective="survey x",
                               task_id="t1"))
    assert res.ok
    # the raw model text is captured, not discarded — and it's the actual reply
    assert res.raw_generation
    assert "summary" in res.raw_generation


def test_record_run_persists_raw_generation(cfg):
    store = ProjectStore(cfg)
    router = LLMRouter(cfg, backends={"mock": MockBackend()})
    registry = make_default_registry()
    runner = SubAgentRunner(cfg, router, registry)
    director = Director(cfg, store, router, registry, runner)
    project, _ = director.new_project("cap", "ship a verified toy")
    director.advance(project.id, force=True)
    reloaded = store.load(project.id)
    runs = list(reloaded.runs.values())
    assert runs and any(r.raw_generation for r in runs)
```

### Step 2 — Run it (expected FAIL)

```
python -m pytest tests/test_stream_capture.py -q
```

Expected: FAIL — `AgentResult.__init__() got an unexpected keyword`/`AttributeError: ... 'raw_generation'`.

### Step 3 — Implement

**(a)** In `E:\director2\director\agents\base.py`, add the field to `AgentResult`. Anchor:

```python
@dataclass
class AgentResult:
    spec_id: str
    task_id: str = ""
    role: str = ""
    ok: bool = False
    output: dict = field(default_factory=dict)
    reports: list[VerificationReport] = field(default_factory=list)
    needs_human: bool = False
    backend: str = ""
    model: str = ""
    usage: dict = field(default_factory=dict)
    latency_s: float = 0.0
    error: str = ""
```

Replace with:

```python
@dataclass
class AgentResult:
    spec_id: str
    task_id: str = ""
    role: str = ""
    ok: bool = False
    output: dict = field(default_factory=dict)
    reports: list[VerificationReport] = field(default_factory=list)
    needs_human: bool = False
    backend: str = ""
    model: str = ""
    usage: dict = field(default_factory=dict)
    latency_s: float = 0.0
    error: str = ""
    # the raw model GENERATION text behind this result (was fetched then
    # discarded). Pure upside even without streaming: a post-hoc replay/inspect
    # view. Honest label: generation, not reasoning.
    raw_generation: str = ""
```

**(b)** In `E:\director2\director\core\types.py`, add the field to `AgentRun`. Anchor:

```python
@dataclass
class AgentRun:
    task_id: str
    role: str
    id: str = field(default_factory=new_id)
    backend: str = ""
    model: str = ""
    status: str = "pending"                   # pending | succeeded | failed
    output: dict = field(default_factory=dict)
    reports: list[VerificationReport] = field(default_factory=list)
    usage: dict = field(default_factory=dict)  # prompt_tokens, completion_tokens
    latency_s: float = 0.0
    error: str = ""
    started_at: datetime = field(default_factory=utcnow)
    completed_at: datetime | None = None
```

Replace with:

```python
@dataclass
class AgentRun:
    task_id: str
    role: str
    id: str = field(default_factory=new_id)
    backend: str = ""
    model: str = ""
    status: str = "pending"                   # pending | succeeded | failed
    output: dict = field(default_factory=dict)
    reports: list[VerificationReport] = field(default_factory=list)
    usage: dict = field(default_factory=dict)  # prompt_tokens, completion_tokens
    latency_s: float = 0.0
    error: str = ""
    # the raw model GENERATION text behind this run (round-trips via the
    # generic encode/decode — zero migration). Generation, not reasoning.
    raw_generation: str = ""
    started_at: datetime = field(default_factory=utcnow)
    completed_at: datetime | None = None
```

**(c)** In `E:\director2\director\agents\runner.py`, capture the raw text. Anchor (inside `run`):

```python
            resp = getattr(out, "_llm_response", None)
            output = out.model_dump()
            output["task_id"] = spec.task_id
            result.output = output
            if resp is not None:
                result.backend = resp.backend
                result.model = resp.model
                result.latency_s = resp.latency_s
                result.usage = {"prompt_tokens": resp.prompt_tokens,
                                "completion_tokens": resp.completion_tokens}
```

Replace with:

```python
            resp = getattr(out, "_llm_response", None)
            output = out.model_dump()
            output["task_id"] = spec.task_id
            result.output = output
            if resp is not None:
                result.backend = resp.backend
                result.model = resp.model
                result.latency_s = resp.latency_s
                result.usage = {"prompt_tokens": resp.prompt_tokens,
                                "completion_tokens": resp.completion_tokens}
                # capture the raw generation (was discarded): post-hoc replay +
                # the live-stream's persisted record of what the model wrote
                result.raw_generation = resp.text
```

**(d)** In `E:\director2\director\core\director.py`, copy it through `_record_run`. Anchor:

```python
    def _record_run(self, project: Project, spec: AgentSpec, res) -> AgentRun:
        run = AgentRun(task_id=spec.task_id, role=spec.role,
                       backend=res.backend, model=res.model,
                       status="succeeded" if res.ok else "failed",
                       output=res.output, reports=res.reports,
                       usage=res.usage, latency_s=res.latency_s,
                       error=res.error, completed_at=utcnow())
        project.runs[run.id] = run
        return run
```

Replace with:

```python
    def _record_run(self, project: Project, spec: AgentSpec, res) -> AgentRun:
        run = AgentRun(task_id=spec.task_id, role=spec.role,
                       backend=res.backend, model=res.model,
                       status="succeeded" if res.ok else "failed",
                       output=res.output, reports=res.reports,
                       usage=res.usage, latency_s=res.latency_s,
                       error=res.error,
                       raw_generation=getattr(res, "raw_generation", ""),
                       completed_at=utcnow())
        project.runs[run.id] = run
        return run
```

### Step 4 — Run it (expected PASS)

```
python -m pytest tests/test_stream_capture.py -q
```

Expected: 4 passed.

### Step 5 — Full suite (OFF byte-identical check)

```
python -m pytest -q
```

Expected: green. `raw_generation` defaults `""` and round-trips through the generic `decode` (which ignores unknown keys and fills defaults), so older snapshots still decode.

### Step 6 — Commit

```
git add director/agents/base.py director/core/types.py director/agents/runner.py director/core/director.py tests/test_stream_capture.py
git commit -m "feat(stream): capture+persist raw_generation on AgentResult/AgentRun (was discarded)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

# Phase 3 — Plan-surface streaming

**Outcome:** when `cfg.stream_generation` is on AND a sink is supplied, `_plan()` streams its `PlanOut` generation via `stream_structured(on_event=sink)`; with the gate off (or no sink) `_plan()` uses `structured()` unchanged. `new_project()` threads an optional sink. `python -m pytest` GREEN.

## Task 3.1 — `_plan` and `new_project` accept an optional sink

**Files:**
- `E:\director2\director\core\director.py` (modify — `new_project`, `_plan`)
- `E:\director2\tests\test_stream_plan.py` (create)

### Step 1 — Write the failing test

Create `E:\director2\tests\test_stream_plan.py`:

```python
"""Plan-surface streaming (Phase 3). Offline mock; gate-on vs gate-off."""

from director.agents.runner import SubAgentRunner
from director.core.director import Director, PlanOut
from director.core.state import ProjectStore
from director.llm.mock import MockBackend
from director.llm.router import LLMRouter
from director.verify import make_default_registry


def _director(cfg):
    store = ProjectStore(cfg)
    router = LLMRouter(cfg, backends={"mock": MockBackend()})
    registry = make_default_registry()
    runner = SubAgentRunner(cfg, router, registry)
    return Director(cfg, store, router, registry, runner), store


def test_plan_streams_when_gated_on_with_sink(cfg):
    cfg.stream_generation = True
    director, _ = _director(cfg)
    events = []
    plan = director._plan("build a verified toy", on_event=events.append)
    assert isinstance(plan, PlanOut) and plan.tasks
    deltas = [e for e in events if e.get("type") == "text_delta"]
    assert deltas and deltas[0]["text"]            # generation streamed
    assert not any(e.get("type") == "thinking_delta" for e in events)


def test_plan_does_not_stream_when_gate_off(cfg):
    cfg.stream_generation = False                  # default
    director, _ = _director(cfg)
    events = []
    plan = director._plan("build a verified toy", on_event=events.append)
    assert isinstance(plan, PlanOut) and plan.tasks
    assert events == []                            # OFF byte-identical: no deltas


def test_plan_no_sink_is_unchanged(cfg):
    cfg.stream_generation = True
    director, _ = _director(cfg)
    plan = director._plan("build a verified toy")  # no on_event
    assert isinstance(plan, PlanOut) and plan.tasks


def test_new_project_threads_sink_when_gated(cfg):
    cfg.stream_generation = True
    director, store = _director(cfg)
    events = []
    project, packet = director.new_project("streamed", "ship verified x",
                                           on_event=events.append)
    assert project.tasks and packet
    assert any(e.get("type") == "text_delta" for e in events)


def test_new_project_no_sink_default_call_still_works(cfg):
    director, store = _director(cfg)
    project, packet = director.new_project("plain", "ship verified x")
    assert project.tasks and packet
```

### Step 2 — Run it (expected FAIL)

```
python -m pytest tests/test_stream_plan.py -q
```

Expected: FAIL — `_plan() got an unexpected keyword argument 'on_event'` / `new_project() got an unexpected keyword argument 'on_event'`.

### Step 3 — Implement

In `E:\director2\director\core\director.py`:

**(a)** `new_project` — add the optional sink and pass it to `_plan`. Anchor:

```python
    def new_project(self, name: str, objective: str) -> tuple[Project, CommandPacket]:
        prev_current = self.store.get_current()
        project = self.store.create(name)
        try:
            plan = self._plan(objective)
            self._ingest_plan(project, objective, plan)
```

Replace with:

```python
    def new_project(self, name: str, objective: str, *,
                    on_event=None) -> tuple[Project, CommandPacket]:
        prev_current = self.store.get_current()
        project = self.store.create(name)
        try:
            plan = self._plan(objective, on_event=on_event)
            self._ingest_plan(project, objective, plan)
```

**(b)** `_plan` — choose `stream_structured` when gated on with a sink; else `structured()` unchanged. Anchor:

```python
    def _plan(self, objective: str) -> PlanOut:
        user = (f"objective: {objective}\n\n"
                f"Available agent roles: {', '.join(role_names())}")
        plan: PlanOut = self.router.structured(
            PLAN_SYSTEM.format(roles=", ".join(role_names())), user,
            PlanOut, role="director", kind="initial_plan")
        # semantic validation beyond schema
```

Replace with:

```python
    def _plan(self, objective: str, *, on_event=None) -> PlanOut:
        user = (f"objective: {objective}\n\n"
                f"Available agent roles: {', '.join(role_names())}")
        sys_prompt = PLAN_SYSTEM.format(roles=", ".join(role_names()))
        # GATED: stream the plan's generation to the sink ONLY when both the
        # gate is on AND a sink is present. Otherwise the call is byte-identical
        # to before (structured()). stream_structured shares structured()'s
        # parse/validate, so the returned PlanOut is identical either way.
        if self.cfg.stream_generation and on_event is not None:
            plan: PlanOut = self.router.stream_structured(
                sys_prompt, user, PlanOut, on_event=on_event,
                role="director", kind="initial_plan")
        else:
            plan = self.router.structured(
                sys_prompt, user, PlanOut, role="director", kind="initial_plan")
        # semantic validation beyond schema
```

### Step 4 — Run it (expected PASS)

```
python -m pytest tests/test_stream_plan.py -q
```

Expected: 5 passed.

### Step 5 — Full suite (the OFF path must be unchanged for every existing `new_project` caller)

```
python -m pytest -q
```

Expected: green. Existing callers pass no `on_event` and/or run with `stream_generation=False`, so `_plan` takes the unchanged `structured()` branch.

### Step 6 — Commit

```
git add director/core/director.py tests/test_stream_plan.py
git commit -m "feat(stream): _plan streams via stream_structured when gated+sink; new_project threads it

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

# Phase 4 — Dashboard SSE + UI pane

**Outcome:** `BridgeHub` gains a thread-safe per-project delta buffer + cursor + a sink factory the background `new`/`advance` thread uses; `GET /api/project/{id}/stream` serves SSE (`text/event-stream`, `data: {json}\n\n`, terminal sentinel); `ui.py` opens an `EventSource` into a new honestly-labeled "Live generation" pane with a dormant `thinking_delta` branch. `python -m pytest` GREEN. No browser / no live call in tests.

## Task 4.1 — `BridgeHub` stream buffer + cursor + sink

The buffer is a per-project append-only list of events under `self._lock` (mirrors the existing `_op` discipline), with a monotonic length used as a cursor. A `_make_stream_sink(pid)` returns a closure that appends `text_delta` events; a `_close_stream(pid)` appends the terminal sentinel; `_stream_since(pid, cursor)` returns `(events, new_cursor)`. The `new` background op is wired to push deltas (and the sentinel on completion); since `new_project` runs with a fresh project id assigned inside `director.new_project`, we buffer under a stable key and let the SSE route read by project id once it exists — but for `/api/new` the project id is not known until the op returns. To keep this concrete and testable, we key the live buffer by the **op** when the pid is unknown, and ALSO by pid for `advance`. The tests below drive the buffer API directly (the spec's required test shape) and the `/stream` route by pid — no browser, no live call.

**Files:**
- `E:\director2\director\dashboard\server.py` (modify — `BridgeHub`)
- `E:\director2\tests\test_stream_sse.py` (create)

### Step 1 — Write the failing test

Create `E:\director2\tests\test_stream_sse.py`:

```python
"""Dashboard SSE side-channel + UI pane (Phase 4). Drives the BridgeHub buffer
directly and the /stream route over loopback — no browser, no live backend."""

import json
import threading
import time
import urllib.request

import pytest

from director.agents.runner import SubAgentRunner
from director.core.director import Director
from director.core.state import ProjectStore
from director.dashboard.server import BridgeHub, make_server
from director.dashboard.ui import INDEX_HTML
from director.llm.mock import MockBackend
from director.llm.router import LLMRouter
from director.verify import make_default_registry


@pytest.fixture()
def hub(cfg):
    store = ProjectStore(cfg)
    router = LLMRouter(cfg, backends={"mock": MockBackend()})
    registry = make_default_registry()
    runner = SubAgentRunner(cfg, router, registry)
    director = Director(cfg, store, router, registry, runner)
    return BridgeHub(cfg, director=director, store=store)


# ----------------------------------------------------- buffer + cursor API
def test_stream_buffer_accumulates_and_cursors(hub):
    sink = hub._make_stream_sink("p1")
    sink({"type": "text_delta", "text": "A"})
    sink({"type": "text_delta", "text": "B"})
    events, cursor = hub._stream_since("p1", 0)
    assert [e["text"] for e in events] == ["A", "B"]
    assert cursor == 2
    # incremental read from the cursor returns only the new ones
    sink({"type": "text_delta", "text": "C"})
    events2, cursor2 = hub._stream_since("p1", cursor)
    assert [e["text"] for e in events2] == ["C"] and cursor2 == 3


def test_close_stream_appends_sentinel(hub):
    hub._make_stream_sink("p2")({"type": "text_delta", "text": "x"})
    hub._close_stream("p2")
    events, _ = hub._stream_since("p2", 0)
    assert events[-1]["type"] == "done"          # terminal sentinel


def test_stream_sink_never_emits_thinking(hub):
    # truth-in-labeling: the sink path only carries the events handed to it; the
    # claude_cli backend never produces thinking_delta, so none can appear here
    sink = hub._make_stream_sink("p3")
    sink({"type": "text_delta", "text": "g"})
    events, _ = hub._stream_since("p3", 0)
    assert not any(e["type"] == "thinking_delta" for e in events)


# ------------------------------------------------------------- SSE route
@pytest.fixture()
def live(hub):
    srv = make_server(hub, port=0)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    yield hub, base
    srv.shutdown()


def test_sse_route_yields_deltas_then_sentinel(live):
    hub, base = live
    # pre-seed the buffer, then close it, so the SSE drain terminates promptly
    sink = hub._make_stream_sink("proj-sse")
    sink({"type": "text_delta", "text": "hello "})
    sink({"type": "text_delta", "text": "world"})
    hub._close_stream("proj-sse")
    with urllib.request.urlopen(base + "/api/project/proj-sse/stream",
                                timeout=5) as r:
        assert r.headers.get("Content-Type", "").startswith("text/event-stream")
        body = r.read().decode("utf-8")
    # SSE framing: each event on its own `data: {json}` line, blank-line separated
    payloads = [json.loads(ln[len("data:"):].strip())
                for ln in body.splitlines() if ln.startswith("data:")]
    texts = [p["text"] for p in payloads if p.get("type") == "text_delta"]
    assert texts == ["hello ", "world"]
    assert payloads[-1]["type"] == "done"        # closed on the terminal sentinel


# ----------------------------------------------------------------- UI pane
def test_ui_has_live_generation_pane_and_eventsource():
    low = INDEX_HTML.lower()
    assert "eventsource" in low                   # opens the SSE channel
    assert "/stream" in low
    assert "live generation" in low               # the honestly-labeled pane
    # honest header: generation, NOT hidden reasoning
    assert "not hidden reasoning" in low
    # the reserved-but-dormant upgrade seam exists in the renderer
    assert "thinking_delta" in low
    # truth-in-labeling: the pane is never called "thinking"
    assert "watch it think" not in low


def test_ui_stays_offline_self_contained():
    low = INDEX_HTML.lower()
    for bad in ("http://", "https://", "cdn.", "googleapis"):
        assert bad not in low
```

### Step 2 — Run it (expected FAIL)

```
python -m pytest tests/test_stream_sse.py -q
```

Expected: FAIL — `AttributeError: 'BridgeHub' object has no attribute '_make_stream_sink'`; the UI tests fail (`eventsource`/`live generation` not present yet).

### Step 3 — Implement (BridgeHub buffer + sink)

In `E:\director2\director\dashboard\server.py`:

**(a)** Add the buffer + the `new`-op wiring. First, initialize the buffer in `__init__`. Anchor (end of `BridgeHub.__init__`):

```python
        self.director = director
        self._lock = threading.Lock()
        self._op = {"running": False, "kind": "", "project": "",
                    "started_at": "", "elapsed_s": 0.0,
                    "result": None, "error": ""}
        self._op_t0 = 0.0
```

Replace with:

```python
        self.director = director
        self._lock = threading.Lock()
        self._op = {"running": False, "kind": "", "project": "",
                    "started_at": "", "elapsed_s": 0.0,
                    "result": None, "error": ""}
        self._op_t0 = 0.0
        # live generation side-channel: per-stream-key append-only event lists,
        # guarded by _lock (mirrors the _op discipline). The cursor is just the
        # list length, so an SSE reader resumes from where it left off. Keyed by
        # project id for advance; by the op key "new" until the project id exists.
        self._streams: dict[str, list[dict]] = {}
```

**(b)** Add the buffer methods. Insert immediately AFTER `__init__` (before the `# ----- reads` section / `overview`). Anchor — the line just before `def overview`:

```python
    # ------------------------------------------------------------------ reads
    def overview(self) -> dict:
```

Replace with:

```python
    # -------------------------------------------------------- live generation
    def _make_stream_sink(self, key: str):
        """Return a thread-safe sink closure that appends generation events to
        ``key``'s buffer. The closure is handed to the Director plan surface and
        is called from the background advance/new-project thread; it mirrors the
        _op lock discipline. Best-effort: it never raises into the model call."""
        def sink(event: dict) -> None:
            try:
                with self._lock:
                    self._streams.setdefault(key, []).append(dict(event))
            except Exception:                                 # noqa: BLE001
                pass
        return sink

    def _close_stream(self, key: str) -> None:
        """Append the terminal sentinel so an SSE reader knows the run is done."""
        with self._lock:
            self._streams.setdefault(key, []).append({"type": "done"})

    def _stream_since(self, key: str, cursor: int) -> tuple[list[dict], int]:
        """Return (new events after ``cursor``, new cursor). Read-only over the
        buffer under the lock — the SSE loop polls this and never mutates."""
        with self._lock:
            buf = self._streams.get(key, [])
            new = buf[cursor:]
            return [dict(e) for e in new], len(buf)

    def _stream_has_sentinel(self, key: str) -> bool:
        with self._lock:
            buf = self._streams.get(key, [])
            return bool(buf) and buf[-1].get("type") == "done"

    def _reset_stream(self, key: str) -> None:
        """Clear a key's buffer at the start of a fresh op so a new run doesn't
        replay the previous run's deltas."""
        with self._lock:
            self._streams[key] = []

    # ------------------------------------------------------------------ reads
    def overview(self) -> dict:
```

**(c)** Wire the `new` background op to stream into the `"new"` key and close it. The route handler (`do_POST` → `/api/new`) builds `_create`; rewire it to pass a sink and finalize the stream. Anchor in `_Handler.do_POST`:

```python
            if path == "/api/new":
                body = self._body()
                name = str(body.get("name", "")).strip()
                objective = str(body.get("objective", "")).strip()
                if not name or not objective:
                    self._send(400, {"error": "name and objective required"})
                    return

                def _create():
                    proj, _ = self.hub.director.new_project(name, objective)
                    return {"project": proj.id, "name": proj.name}

                out = self.hub.start_background("new", "", _create)
                self._send(out.pop("status", 202) if isinstance(
                    out.get("status"), int) else 202, out)
```

Replace with:

```python
            if path == "/api/new":
                body = self._body()
                name = str(body.get("name", "")).strip()
                objective = str(body.get("objective", "")).strip()
                if not name or not objective:
                    self._send(400, {"error": "name and objective required"})
                    return
                self.hub._reset_stream("new")
                sink = self.hub._make_stream_sink("new")

                def _create():
                    try:
                        proj, _ = self.hub.director.new_project(
                            name, objective, on_event=sink)
                        return {"project": proj.id, "name": proj.name}
                    finally:
                        self.hub._close_stream("new")

                out = self.hub.start_background("new", "", _create)
                self._send(out.pop("status", 202) if isinstance(
                    out.get("status"), int) else 202, out)
```

> When `cfg.stream_generation` is off, `new_project(..., on_event=sink)` still works — `_plan` ignores the sink (gate off), the buffer stays empty, and `_close_stream` writes only the sentinel. OFF byte-identical: the sink is accepted but never called.

### Step 4 — Implement (SSE route)

In `E:\director2\director\dashboard\server.py`, add the SSE GET route. The stdlib handler writes the raw response itself (no `Content-Length`, flushes per event, bounded drain loop that sleeps briefly between polls and closes on the sentinel). Anchor in `_Handler.do_GET` — the integrity route just before the `else 404`:

```python
            elif m := re.fullmatch(r"/api/project/([\w-]+)/integrity", path):
                self._send(200, self.hub.integrity(m.group(1)))
            else:
                self._send(404, {"error": f"no route {path}"})
```

Replace with:

```python
            elif m := re.fullmatch(r"/api/project/([\w-]+)/integrity", path):
                self._send(200, self.hub.integrity(m.group(1)))
            elif m := re.fullmatch(r"/api/project/([\w-]+)/stream", path):
                self._sse(m.group(1))
            else:
                self._send(404, {"error": f"no route {path}"})
```

Then add the `_sse` method to `_Handler`. Insert it immediately AFTER `_body` (before `do_GET`). Anchor:

```python
    def _body(self) -> dict:
        try:
            n = int(self.headers.get("Content-Length", 0) or 0)
            return json.loads(self.rfile.read(n) or b"{}")
        except (json.JSONDecodeError, ValueError):
            raise DirectorError("request body is not valid JSON")
```

Replace with:

```python
    def _body(self) -> dict:
        try:
            n = int(self.headers.get("Content-Length", 0) or 0)
            return json.loads(self.rfile.read(n) or b"{}")
        except (json.JSONDecodeError, ValueError):
            raise DirectorError("request body is not valid JSON")

    def _sse(self, pid: str) -> None:
        """Server-Sent Events drain of the live-generation buffer. The dashboard
        keys new-project generation under "new" until the project id exists, so
        accept BOTH the project id and that op key. text/event-stream, no
        Content-Length, flush per event, bounded poll loop, close on the terminal
        sentinel — so a long-lived SSE response can't starve the threaded server.
        Read-only over the buffer (the sink is the only writer)."""
        key = pid
        # the in-flight new-project op streams under "new"; route a request for
        # the still-unnamed project (or the literal 'new' key) onto it
        with self.hub._lock:
            has_pid = key in self.hub._streams
        if not has_pid and self.hub._op.get("kind") == "new":
            key = "new"
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        cursor = 0
        deadline = time.time() + 600          # hard cap: never hang a thread forever
        try:
            while time.time() < deadline:
                events, cursor = self.hub._stream_since(key, cursor)
                done = False
                for ev in events:
                    self.wfile.write(
                        ("data: " + json.dumps(ev, default=str)
                         + "\n\n").encode("utf-8"))
                    if ev.get("type") == "done":
                        done = True
                self.wfile.flush()
                if done:
                    break
                # no new events: if the buffer is already sentinel-terminated we
                # are finished; otherwise yield the thread briefly and re-poll
                if not events and self.hub._stream_has_sentinel(key):
                    break
                if not events:
                    time.sleep(0.1)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass     # client disconnected — best-effort observability, no error
```

### Step 5 — Implement (UI pane)

In `E:\director2\director\dashboard\ui.py`, add the EventSource + "Live generation" pane. Three small splices:

**(a)** Add the pane container into the project view. The pane MUST be a **sibling of `.scroll`**, NOT inside `#thread` — `renderThread()` does `$("#thread").innerHTML=h`, which would wipe a pane living inside `#thread` on every re-render. Anchor (inside `renderProject`):

```javascript
    <div class="scroll"><div class="col" id="thread"></div></div>
    <div class="composer" id="composer"></div>`;
  renderThread();renderComposer();
}
```

Replace with exactly this (note the single closing backtick after `</div>` on the `composer` line — do not add any extra backtick):

```javascript
    <div class="scroll"><div class="col" id="thread"></div></div>
    <div id="livegen" class="livegen" hidden>
      <div class="lgh">Live generation
        <span class="lgsub">model output as it's written — not hidden reasoning
        (the subscription backend doesn't expose reasoning)</span></div>
      <pre id="livegen-body" class="lgbody mono"></pre></div>
    <div class="composer" id="composer"></div>`;
  renderThread();renderComposer();
}
```

**(b)** Add minimal CSS for the pane. Anchor (the `.composer` rule near the styles):

```css
.composer{border-top:1px solid var(--line);padding:14px 28px}
```

Replace with:

```css
.composer{border-top:1px solid var(--line);padding:14px 28px}
/* live generation pane — visually SEPARATE from verified artifacts/decisions;
   honestly labeled generation (not reasoning). thinking-delta styling is the
   reserved-but-dormant upgrade seam (claude_cli never emits it). */
.livegen{border-top:1px solid var(--line2);background:rgba(55,224,245,.04);
  padding:10px 28px;max-height:200px;overflow:auto}
.livegen .lgh{font-size:11.5px;letter-spacing:.5px;text-transform:uppercase;
  color:var(--accent-dim);display:flex;flex-direction:column;gap:2px}
.livegen .lgsub{text-transform:none;letter-spacing:0;color:var(--faint);
  font-size:11px}
.livegen .lgbody{white-space:pre-wrap;word-break:break-word;color:var(--dim);
  font-size:12.5px;margin:6px 0 0}
.livegen .think{color:var(--pivot)}     /* dormant: reserved thinking_delta tier */
```

**(c)** Add the `openLiveGen(pid)` helper that opens an `EventSource` and appends deltas. INSERT it as a new function immediately BEFORE the existing `async function op(kind,force){` (do NOT modify `op` itself). Anchor — the existing `op` function (locate it; insert the new function directly above this line):

```javascript
async function op(kind,force){
  try{const out=await jpost(api+"/project/"+CUR+"/"+kind,{force:!!force});
    if(out.error)toast(out.error,true);else toast(kind+" started…");pollOp();
  }catch(e){toast(""+e.message,true);}
}
```

Insert this new function ABOVE that `op` function (leaving `op` itself exactly as-is):

```javascript
/* live generation: open an SSE channel and append GENERATION deltas to the
   honestly-labeled pane. A reserved thinking_delta branch is present but dormant
   — claude_cli never emits it (the upgrade seam for an Anthropic-API backend). */
let liveSrc=null;
function openLiveGen(pid){
  if(liveSrc){try{liveSrc.close();}catch(e){}}
  const pane=$("#livegen"),body=$("#livegen-body");
  if(!pane||!body)return;
  body.textContent="";        // OFF byte-identical at the UI: the pane stays
                              // HIDDEN until a REAL delta arrives, so a gate-off
                              // run (no deltas, only the sentinel) shows nothing.
  try{liveSrc=new EventSource(api+"/project/"+pid+"/stream");}
  catch(e){return;}
  liveSrc.onmessage=ev=>{
    let d;try{d=JSON.parse(ev.data);}catch(_){return;}
    if(d.type==="text_delta"){
      pane.hidden=false;                            /* reveal on first generation */
      body.appendChild(document.createTextNode(d.text||""));
      pane.scrollTop=pane.scrollHeight;
    }else if(d.type==="thinking_delta"){            /* dormant reserved tier */
      pane.hidden=false;
      const s=document.createElement("span");s.className="think";
      s.textContent=d.text||"";body.appendChild(s);
      pane.scrollTop=pane.scrollHeight;
    }else if(d.type==="done"){
      try{liveSrc.close();}catch(_){}
      liveSrc=null;
    }
  };
  liveSrc.onerror=()=>{try{liveSrc.close();}catch(_){}liveSrc=null;};
}
```

> `op(kind)` (advance/finalize) is INTENTIONALLY left unchanged in this version. Per spec §9 this version streams the PLAN surface only (`new_project`/`_plan`); advance/packet streaming is a documented follow-on that reuses this exact `openLiveGen` plumbing. Do NOT call `openLiveGen` from `op('advance')` here — there is no advance-side sink wired, so it would only show an empty pane that waits to the SSE deadline. `openLiveGen` is added now (used by `createProject` below) so the follow-on is a one-line wire-up.

Anchor — `createProject()` (open the stream under the "new" key — the route maps it to the in-flight new op):

```javascript
  try{const out=await jpost(api+"/new",{name,objective:obj});
    if(out.error){toast(out.error,true);return;}
    pendingNew=true;toast("Planning…");
    $("#main").innerHTML=`<div class="empty">Drawing up the plan…</div>`;pollOp();
  }catch(e){toast(""+e.message,true);}
```

Replace with:

```javascript
  try{const out=await jpost(api+"/new",{name,objective:obj});
    if(out.error){toast(out.error,true);return;}
    pendingNew=true;toast("Planning…");
    $("#main").innerHTML=`<div class="newform"><h2>Drawing up the plan…</h2>
      <div id="livegen" class="livegen" hidden>
        <div class="lgh">Live generation
          <span class="lgsub">model output as it's written — not hidden reasoning
          (the subscription backend doesn't expose reasoning)</span></div>
        <pre id="livegen-body" class="lgbody mono"></pre></div></div>`;
    openLiveGen("new");
    pollOp();
  }catch(e){toast(""+e.message,true);}
```

### Step 6 — Run it (expected PASS)

```
python -m pytest tests/test_stream_sse.py -q
```

Expected: all pass. (The SSE test pre-seeds + closes the buffer, so the drain returns promptly with the deltas and the `done` sentinel.)

### Step 7 — Full suite

```
python -m pytest -q
```

Expected: green. The existing `test_dashboard.py::test_index_html_self_contained` and `test_ui_synthesis_structure` still pass (no external URLs added; all required tokens still present). The `/api/new` op still returns `{"status":"started"}` and yields the project id — the sink is additive and OFF byte-identical when the gate is off.

### Step 8 — Commit

```
git add director/dashboard/server.py director/dashboard/ui.py tests/test_stream_sse.py
git commit -m "feat(stream): dashboard SSE side-channel + honest Live generation pane

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

# Phase 5 — Gate/parity checkpoint

**Outcome:** full suite green; OFF byte-identical re-confirmed end to end; checkpoint commit.

## Task 5.1 — Full-suite parity + OFF byte-identical confirmation

**Files:** none changed (verification + a checkpoint test).

### Step 1 — Add the explicit OFF-parity test

Append to `E:\director2\tests\test_stream_plan.py`:

```python
def test_off_path_uses_structured_not_stream(cfg, monkeypatch):
    # OFF byte-identical, proven by interception: with the gate off, _plan must
    # call router.structured and must NOT call router.stream_structured
    cfg.stream_generation = False
    director, _ = _director(cfg)
    calls = {"structured": 0, "stream": 0}
    real_structured = director.router.structured

    def spy_structured(*a, **k):
        calls["structured"] += 1
        return real_structured(*a, **k)

    def spy_stream(*a, **k):
        calls["stream"] += 1
        raise AssertionError("stream_structured must not run when gate is OFF")

    monkeypatch.setattr(director.router, "structured", spy_structured)
    monkeypatch.setattr(director.router, "stream_structured", spy_stream)
    plan = director._plan("ship x", on_event=lambda e: None)
    assert plan.tasks
    assert calls["structured"] == 1 and calls["stream"] == 0
```

### Step 2 — Run the targeted test (expected PASS)

```
python -m pytest tests/test_stream_plan.py::test_off_path_uses_structured_not_stream -q
```

Expected: 1 passed.

### Step 3 — Run the FULL suite

```
python -m pytest -q
```

Expected: GREEN. Count = 414 pre-existing + all new tests across `test_stream_config.py`, `test_stream_backend.py`, `test_stream_capture.py`, `test_stream_plan.py`, `test_stream_sse.py`. No pre-existing test modified.

### Step 4 — Confirm `complete()` / `structured()` were not touched

```
git diff --stat bc4f9aa -- director/llm/base.py director/llm/router.py director/llm/claude_cli.py
git log --oneline bc4f9aa..HEAD
```

Eyeball that the diffs add `stream`/`stream_structured`/`_stream_complete`/`_stream_text_chunks` and the `_argv` `output_format` param ONLY — `complete()` and `structured()` bodies are unchanged.

### Step 5 — Checkpoint commit

```
git add tests/test_stream_plan.py
git commit -m "test(stream): OFF byte-identical parity — _plan uses structured() when gated off

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Appendix A — Honored invariants → where enforced

| Invariant | Enforced by |
|---|---|
| OFF byte-identical | `test_stream_generation_defaults_false`, `test_plan_does_not_stream_when_gate_off`, `test_off_path_uses_structured_not_stream`; full-suite green at every phase |
| Non-breaking core (`complete`/`structured` untouched) | parallel `stream`/`stream_structured` methods; `_argv` keeps `output_format="json"` default so `test_complete_contract` stays green; `git diff` check in Task 5.1 |
| Stream failure can't corrupt result | `ClaudeCliBackend.stream` fallbacks to `complete()` on launch/read/empty errors (`test_claude_stream_falls_back_to_complete_on_launch_error`); router `_stream_complete` fails over like `complete`; final parse/validate is shared `_validate_reply` |
| Truth-in-labeling (`text_delta` now, `thinking_delta` reserved/never emitted) | every backend/router/SSE test asserts no `thinking_delta`; UI carries a dormant `thinking_delta` branch + "not hidden reasoning" header (`test_ui_has_live_generation_pane_and_eventsource`) |
| Explicit-only live, no accidental billing | `Config(backend=...)`/`--backend` only; `detect_backend` logic unchanged; `tests/conftest.py` `DIRECTOR_LIVE_BACKEND` opt-in (default mock) |
| Thread-safe side-channel | `BridgeHub._streams` guarded by the existing `_lock`; SSE loop read-only; sink swallows its own exceptions |

## Appendix B — The capstone live run (manual, NOT a pytest test — spec §12)

Out of scope for automated tests; documented here so the operator can run it after the suite is green:

1. Launch live with streaming on:
   `set DIRECTOR_STREAM_GENERATION=1` then `python -m director dashboard --backend claude_cli --open`
   (or `python -m director new "watch" -o "..." --backend claude_cli` with `DIRECTOR_STREAM_GENERATION=1`).
2. Create a project whose first task fails a trusted check (so the Credit Knife writes a real scar) — or pre-seed a scar to make it quick, documented honestly as in `live_escalate.py`.
3. Re-plan/advance a same-signature follow-up and WATCH the "Live generation" pane: the plan assembling token-by-token, the scar/marker forming, the advisory rerank, and the PRIOR-PAIN diagnosis injected into the next generation.
4. Record what the stream shows. The honest question — does prior pain visibly change what the model writes? — is exploratory; a null is a legitimate result. The point is it is now watchable, not asserted.

## Appendix C — Splice risks the orchestrator should scrutinize at self-review

1. **`renderProject` / `renderThread` clobber.** `renderThread()` does `$("#thread").innerHTML=h`. The `#livegen` pane MUST be a sibling of `.scroll`, not inside `#thread`, or every thread re-render wipes it. Task 4.1 step 5(a) places it as a sibling — confirm the implementer used that exact splice.
2. **SSE in the stdlib threaded server.** `ThreadingHTTPServer` serves each request on its own thread (`daemon_threads=True`), so a long-lived `_sse` drain won't starve others — but the drain MUST terminate: it closes on the `done` sentinel, breaks if the buffer is already sentinel-terminated, and has a 600s hard deadline. Confirm the `_close_stream` sentinel is always written — for `/api/new` it is in the `finally:` of `_create`, so it fires even if planning raises.
3. **`/api/new` project-id-unknown handoff.** New-project generation is buffered under the `"new"` key because the project id isn't known until `new_project` returns. The `_sse` route maps a request for an unknown pid to `"new"` while a `new` op is running. This is the trickiest handoff — the test drives the buffer by an explicit key (`proj-sse`) to keep it deterministic; the `"new"` mapping is exercised only by the manual capstone. **Decided for this version:** only the plan surface streams (spec §9 "plan first"); `op('advance')` is left unchanged and does NOT call `openLiveGen` (no advance-side sink exists yet — calling it would show an empty pane that waits to the deadline). Advance/packet streaming is a documented follow-on that reuses this same plumbing.
4. **Popen line-reader buffering.** `--verbose` is required for `stream-json` to flush per-message (empirical, spec §1). The reader iterates `proc.stdout` line by line with `text=True`; a backend that buffers would defer deltas — acceptable (still correct final text), but note it. The fallback-to-`complete()` on empty/garbled output is the safety net.
5. **`stream_generation` accepted-but-unused sink (OFF).** With the gate off, `new_project(..., on_event=sink)` still threads the sink to `_plan`, which ignores it. Confirm no delta is ever appended in the OFF path (buffer holds only the sentinel) so the dashboard OFF behavior is unchanged.
