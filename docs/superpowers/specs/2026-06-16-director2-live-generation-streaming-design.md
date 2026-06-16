# Director 2.0 — Live Generation Streaming + Watchable Live Runs (design)

- **Date:** 2026-06-16
- **Status:** Approved design (brainstorm complete) — pending implementation plan
- **Project:** Director 2.0 (`E:\director2`), branch `live-streaming` (builds on v1+v2, merged to master)
- **Scope:** Stream the model's *generation* to the web dashboard so the operator can WATCH a live run unfold (plan-first); patch the live-test workflow so live runs are reliable and repeatable on the Max-sub `claude_cli` backend; capture/persist raw generation. Capstone: a documented live run that demonstrates v2's premise (pain → memory → reroute) watchable in the browser. **Out of scope:** real labeled extended-thinking (the subscription CLI does not expose it — see §1); per-cycle/packet streaming (a follow-on that reuses this plumbing).

---

## 1. Premise & the honest constraint

The operator wants to **watch the thinking** a live run does, in the web UI, to see whether "the thinking" changes as we iterate — and to watch v2's learning organs actually reroute behavior. Grounding this against source produced one decisive, honest finding:

**The `claude_cli` backend (Max subscription) cannot surface labeled reasoning.** `claude_cli.py` calls `claude -p --output-format json` (blocking, non-streaming); the returned JSON exposes only the final `result` text — no thinking field. An empirical probe (`claude -p --output-format stream-json --verbose`, even with a "think hard" prompt) emitted only `assistant`/`text`, `result`, and `system` events — **zero thinking blocks**. Real labeled reasoning is available only via the Anthropic API with `thinking:{type:"enabled"}` + `stream:true`, which is metered and flagship-pinned.

**Operator decision (2026-06-16): stay on the subscription `claude_cli` backend.** Therefore what we stream is the model's **output as it is written** — for the planning call, the task graph assembling token-by-token. This is real, watchable observability (you see ordering, hesitation, mid-write revision), but it is **generation, not hidden reasoning**.

**Governing principle (the instrument must not lie about itself).** We label this "live generation," never "thinking," in code and UI. The header reads plainly: *"model output as it's written — not hidden reasoning."* The event protocol nonetheless reserves a `thinking_delta` type that the `claude_cli` backend never emits, so an Anthropic-API backend could later stream real reasoning into the same pane with **no replumbing**. Truth-in-labeling now; a clean upgrade seam for later.

## 1a. Where spontaneity actually lives (corrects the operator's RDE thesis)

The operator believed spontaneous behavior rests on the RDE. Source says otherwise: the RDE-in-Director is `ImprovementLoop` (`evolve/loop.py`), a *sectoral algorithm-discovery* tool invoked only by explicit CLI/API call — **no path from `Director.advance()`/`run()` reaches it**. Novelty actually comes from three model-backed `router.structured(...)` surfaces, ranked: **`_plan()`** (`director.py:346` — invents the entire task graph; highest novelty) > **`_make_packet()`** (`director.py:500`) > **`SubAgentRunner.run()`** (`runner.py:48`). The nervous system *biases and diagnoses* but never generates. This is why we instrument the **generative calls in a normal project** (plan first) rather than the RDE — and it makes the work cleaner (no RDE wiring).

---

## 2. Goals & non-goals

### Goals
- **G1 — Reliable live runs.** Make a live run on `claude_cli` reliable and repeatable from CLI and dashboard; fix the silent mock-fallback; let pytest opt into live without leaking billing into the default suite.
- **G2 — Stream generation to the browser.** Stream the `_plan()` generation token-by-token to the web UI over SSE, rendered in a dedicated, honestly-labeled pane.
- **G3 — Capture/persist generation.** Persist the raw model generation on the run record (also fixes the standing gap where raw text is fetched then discarded).
- **G4 — Watchable v2 premise.** A documented live procedure where a task fails → Credit Knife scars it → Gut Markers recall the diagnosis → the next plan is generated with that pain in context — all watchable in the browser.

### Non-goals
- **Not** real labeled extended-thinking (subscription CLI can't; reserved seam only).
- **Not** per-cycle/packet/subagent streaming yet (follow-on; reuses the same protocol + SSE + pane).
- **Not** any change to the verify-before-ingest pipeline, the nervous system, or the deterministic bench. Streaming is **additive observability**; the parse/ingest path is unchanged.
- **Not** a new web framework or dependency — the dashboard stays a stdlib HTTP handler; transport is plain SSE.

---

## 3. Governing constraints

- **(a) OFF byte-identical.** All streaming is gated by `cfg.stream_generation` (default **False**). With it off, no streaming code runs and behavior is byte-identical; the existing suite stays green.
- **(b) Non-breaking core.** `complete()`/`structured()` are untouched. Streaming adds parallel methods (`stream()`, `stream_structured()`); the final parse/return is identical to non-streaming.
- **(c) Truth-in-labeling.** The streamed channel is named *generation*/*output*, never *thinking*. Event types are explicit (`text_delta` now; `thinking_delta` reserved, unused by `claude_cli`).
- **(d) Verify-before-ingest preserved.** Streamed generation is **un-verified** and is rendered in a pane visually separate from verified artifacts. Streaming never short-circuits verification; the parsed result is still verified/ingested exactly as today.
- **(e) Explicit live opt-in, no silent billing.** `claude_cli` stays explicit-only (we do NOT autodetect it from an OAuth token — that fights the existing safety design). Live is selected by an explicit `--backend`/`Config(backend=...)` or `DIRECTOR_BACKEND`; tests stay mock unless `DIRECTOR_LIVE_BACKEND` opts in.
- **(f) Thread-safe side-channel.** The LLM call runs inside the runner's `ThreadPoolExecutor` and the dashboard's background advance thread; the stream travels a thread-safe queue, mirroring the dashboard's existing `_lock`/`_op` discipline. No async rewrite of the runner.

---

## 4. Architecture overview

A backend-agnostic **event protocol** carried by a **callback sink** from the backend up to a per-project queue on the dashboard, drained to the browser over **SSE**.

```
ClaudeCLIBackend.stream(system, user, *, on_event)        # Popen + stream-json line reader
        emits on_event({"type":"text_delta","text": chunk, ...})
   -> LLMRouter.stream_structured(..., on_event)          # accumulate text, parse final -> schema
   -> SubAgentRunner / Director._plan (sink wired)         # pass sink; capture raw_generation
   -> BridgeHub._stream_q  (thread-safe queue + cursor)    # dashboard side-channel
   -> GET /api/project/{id}/stream  (text/event-stream)    # SSE drain
   -> ui.py EventSource -> "Live generation" pane          # honestly labeled
```

| Piece | Home | Nature |
|---|---|---|
| Backend stream | `director/llm/claude_cli.py` (NEW method) | `Popen --output-format stream-json --verbose`; line-by-line; `on_event` per delta |
| Router stream | `director/llm/router.py` (NEW method) | `stream_structured()` mirrors `structured()`, threads `on_event`, parses final |
| Generation capture | `director/agents/base.py`, `director/core/types.py` | new `raw_generation` field on `AgentResult`/`AgentRun` |
| Plan surface | `director/core/director.py` (`_plan`/`new_project`) | use `stream_structured` + sink when gated on |
| Dashboard side-channel + SSE | `director/dashboard/server.py` | `BridgeHub._stream_q` + `GET /api/project/{id}/stream` |
| UI pane | `director/dashboard/ui.py` | `EventSource` + honestly-labeled "Live generation" pane |
| Live-test workflow patch | `director/cli.py`, `director/config.py`, `tests/conftest.py` | `--backend` flag, `DIRECTOR_LIVE_BACKEND` opt-in |
| Gate | `director/config.py` | `stream_generation: bool = False` |

---

## 5. Component — live-test workflow patch (lands first)

**Root cause (verified `config.py:257-265`).** `detect_backend()` returns the explicit `self.backend` if set, else the first provider with an API key, else `mock`. `claude_cli` is **explicit-only** (and `_STRIP_RE` blanks `ANTHROPIC_*`/`CLAUDECODE*` from the child). A non-interactive run without `DIRECTOR_BACKEND=claude_cli` reaching it → `mock`.

**Patch:**
- **`--backend` flag** on the relevant CLI entrypoint(s) and a `Config(backend=...)` path so a live run can be selected directly, robust against a blanked environment (cannot be silently defeated). `live_escalate.py` already prints `detect_backend()` at startup — that line stays the repeatability check.
- **`tests/conftest.py` opt-in.** The fixture that blanks provider keys/`DIRECTOR_BACKEND` honors `DIRECTOR_LIVE_BACKEND`: when set, it does NOT blank for that run, so pytest can go live deliberately. Default stays safe (mock, no billing).
- **No change to `detect_backend` logic.** We do NOT autodetect `claude_cli` (keeps the explicit-only safety design).

## 6. Component — backend streaming (`claude_cli`)

`ClaudeCLIBackend.stream(self, system, user, *, on_event, **kw) -> CompletionResult` (or the backend's existing return type):
- Build argv like `complete()` but `--output-format stream-json --verbose` (keep `-p --max-turns 1 --tools "" --setting-sources "" --no-session-persistence`).
- `subprocess.Popen(argv, stdin=PIPE, stdout=PIPE, text=True, ...)`; write `user` to stdin; read stdout **line by line**; `json.loads` each line.
- For each assistant text delta, call `on_event({"type":"text_delta","text": chunk})`; accumulate into a buffer.
- On the terminal `result` event, finalize: return the same shape `complete()` returns (final text + usage), so callers are unchanged. The accumulated buffer IS the final text.
- Robustness: tolerate non-JSON lines; on process error, surface as the backend's normal error path (the stream is best-effort observability — a stream failure must not corrupt the result; fall back to a blocking `complete()` if the stream cannot be established).
- The `claude_cli` backend NEVER emits `thinking_delta` (it has no reasoning to emit).

## 7. Component — router streaming

`LLMRouter.stream_structured(self, system, user, schema, *, on_event, role=..., kind=...) -> parsed`:
- Mirrors `structured()` (`router.py:172-193`): same backend selection, same prompt assembly, same schema parse/validate of the FINAL accumulated text.
- Threads `on_event` to `backend.stream(...)`. If the selected backend has no `stream()` (e.g. mock), fall back to `structured()` and emit a single `text_delta` with the whole result (so the UI still shows something deterministic in tests).
- Returns the validated schema object exactly as `structured()` does — the only difference is the side-channel of deltas.

## 8. Component — generation capture/persist

- New field `raw_generation: str = ""` on `AgentResult` (`agents/base.py`) and `AgentRun` (`core/types.py`), round-tripping via existing encode/decode (zero migration).
- `SubAgentRunner.run()` already fetches the LLM response at `runner.py:52` and discards `.text` — capture it into `result.raw_generation`. This is pure upside even without streaming: a post-hoc replay/inspect view.
- When gated on and a sink is present, the runner/`_plan` pass the sink so deltas also flow live.

## 9. Component — plan-surface streaming (`_plan` first)

- When `cfg.stream_generation` and a sink is available, `_plan()` (`director.py:346`) issues its `PlanOut` call via `router.stream_structured(on_event=sink)` instead of `structured()`. The streamed deltas are the plan being written; the final parsed `PlanOut` is ingested exactly as today.
- `new_project()` (`director.py:318`) is the dashboard entrypoint that calls `_plan`; the dashboard supplies the sink (a closure that pushes onto `BridgeHub._stream_q`).
- All other generative surfaces (`_make_packet`, subagent roles) are UNCHANGED in this version (follow-on; the protocol/SSE/pane already support them).

## 10. Component — dashboard side-channel + SSE

- **`BridgeHub`** (`server.py:233-269`) gains `self._stream_q: queue.Queue` (or a per-project dict of append-only delta lists with a monotonic cursor) populated by the sink while the background advance/new-project thread runs — guarded by the existing `_lock`, mirroring `_op`.
- **`GET /api/project/{id}/stream`** added to `_Handler.do_GET` (`server.py:317-347`): sets `Content-Type: text/event-stream`, `Cache-Control: no-cache`, no `Content-Length`; loops pulling deltas (from the cursor) and writes `data: {json}\n\n`, flushing each; closes on a terminal sentinel event (run complete). Reuses the existing header/write pattern minus Content-Length.
- The sink is thread-safe; the SSE loop is read-only over the queue/cursor.

## 11. Component — UI "Live generation" pane

- In `ui.py`'s single-file `INDEX_HTML` (the `setInterval`/`pollOp` block ~842-843): when an advance/new-project starts, open `new EventSource('/api/project/{id}/stream')`; append each `text_delta.text` to a dedicated **"Live generation"** pane; close the source on the terminal sentinel (and let the existing `safeRefresh()` fire the final digest refresh so verified state updates normally).
- The pane is **visually separate** from the verified artifact/decision views and carries the honest header: *"model output as it's written — not hidden reasoning (the subscription backend doesn't expose reasoning)."*
- A `thinking_delta` branch is present in the renderer (styled distinctly) but is dormant with `claude_cli` — the reserved upgrade seam.

## 12. Component — the watchable v2 live run (capstone, manual)

A documented procedure (a runnable harness + a short operator script), NOT a pytest test, that demonstrates v2's whole premise live on `claude_cli` with `stream_generation` on:
1. Start the dashboard on the live backend (`--backend claude_cli`, `stream_generation` on).
2. Create a project whose first attempt at a task will fail against a trusted check (so the Credit Knife writes a real scar) — or pre-seed a scar to make the effect deterministic and quick, **documented honestly** as in `live_escalate.py`.
3. Re-plan / advance a follow-up of the same signature and **watch in the browser**: the live generation stream, the scar/marker forming, the advisory rerank, and the PRIOR-PAIN diagnosis injected into the next generation.
4. The honest question stays the honest question: does prior pain visibly change what the model writes? Record what the stream shows; a null is a legitimate result. The point is that it is now **watchable**, not asserted.

---

## 13. Data model, config & file layout

### New config (`director/config.py`)
- `stream_generation: bool = False` — gate; OFF byte-identical.
- `--backend` plumbing → `Config(backend=...)` (already a field; expose via CLI flag).

### New fields
- `AgentResult.raw_generation: str = ""` (`agents/base.py`).
- `AgentRun.raw_generation: str = ""` (`core/types.py`).

### New methods / routes
- `ClaudeCLIBackend.stream(...)`; `LLMRouter.stream_structured(...)`; `BridgeHub._stream_q` + drain; `GET /api/project/{id}/stream`; `ui.py` EventSource + pane.

### Edits (all gated / additive)
- `director/core/director.py` — `_plan` uses `stream_structured` when gated + sink present.
- `director/agents/runner.py` — accept optional sink; capture `raw_generation`.
- `director/cli.py` — `--backend` flag; pass sink from dashboard.
- `tests/conftest.py` — `DIRECTOR_LIVE_BACKEND` opt-in.

---

## 14. Testing plan

- **Unit — router fallback:** `stream_structured` with the mock backend emits one `text_delta` and returns the same validated schema as `structured()` (deterministic, offline).
- **Unit — capture:** a run records `raw_generation` (mock) on `AgentResult`/`AgentRun`; round-trips via encode/decode.
- **Unit — backend stream parser:** feed canned `stream-json` lines to a small parser helper; assert `on_event` is called per `text_delta` and the final text equals the concatenation (no live call — fixture lines).
- **Unit — SSE route:** the `/stream` route yields `text/event-stream` and emits the queued deltas then a terminal sentinel (drive `BridgeHub._stream_q` directly; no browser).
- **Unit — gate/OFF byte-identical:** with `stream_generation=False`, `_plan` uses `structured()` and no stream code runs; the full pre-existing suite stays green.
- **Unit — workflow patch:** `Config(backend="claude_cli")` makes `detect_backend()` return `claude_cli`; `conftest` honors `DIRECTOR_LIVE_BACKEND`.
- **Live (manual, `claude_cli`):** the §12 capstone, observed not asserted (record the trace; the does-pain-change-generation question is exploratory; a null is legitimate).

---

## 15. Risks & open items

- **Stream fragility.** A `stream-json` parse hiccup must never corrupt the result — the final text/parse path is authoritative; streaming is best-effort and falls back to blocking `complete()`/`structured()`. (Constraint §3b/§6.)
- **SSE + stdlib server.** The dashboard's `BaseHTTPRequestHandler` is threaded; a long-lived SSE response must not starve other requests — keep the drain loop bounded (yield/sleep between pulls) and close on the terminal sentinel.
- **"Watch it think" expectation gap.** The operator chose the subscription path knowing it shows generation, not reasoning. The UI labeling (§1, §11) is the mitigation — the instrument states what it is. If real reasoning is ever wanted, the reserved `thinking_delta` + an Anthropic-API backend is the upgrade, no replumbing.
- **Accidental live billing in tests.** Mitigated by explicit-only `claude_cli` + the `DIRECTOR_LIVE_BACKEND` opt-in (default mock).
- **Capstone determinism.** Forcing a real repeated live failure is slow/expensive; the harness may pre-seed a scar to make the effect quick — documented honestly (as in `live_escalate.py`), since the goal is a *watchable* demonstration, not an assertion.
