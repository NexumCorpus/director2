# Grok channels — robust comms harness

`director/llm/grok_channel.py` — the production communications layer for talking to
Grok Build. Supersedes the thin `director/bench/grok_dialogue.py` (which shelled `grok`
and stripped stdout). Built + live-validated 2026-06-18.

## Why it's more robust

| | old `grok_dialogue.py` | `GrokChannel` |
|---|---|---|
| Continuity | replay whole transcript every call | **native `--resume <sessionId>`** — send only the new message |
| Parsing | `stdout.strip()` (tool/plan noise mixed in) | **`--output-format json`** → `{text, sessionId, thought, stopReason}` |
| Store | markdown only | append-only **JSONL** (machine-readable truth) + rendered markdown |
| Reliability | none | retry + backoff on transient (timeout / parse-fail / empty) |
| Fidelity | records raw stdout | records a turn **only if** exit 0 + parses + non-empty; stderr non-fatal |
| Recovery | n/a | native session lost → **re-thread from JSONL** → fresh session |
| Latency | ~15–34 s/turn (replay) | ~10 s/turn (native) |

Verified facts about the CLI behind this design: `--output-format json` returns a
`sessionId`; `--resume <id>` continues it headlessly (recalled a codeword across calls);
the benign stderr `worker quit ... AuthorizationRequired` appears on *healthy* calls and
must not be treated as failure.

## Usage

```python
from director.llm.grok_channel import GrokChannel

c = GrokChannel("my-topic", system="You are Grok, in a research dialogue with Claude.")
turn = c.send("Here's my question ...")
print(turn.content)         # Grok's reply (clean)
print(turn.thought)         # Grok's reasoning, if any
print(turn.ok, turn.error)  # fidelity: ok=False + error on failure, never a fake reply
# c.ping() -> bool health check ; c.render() -> rebuild transcript.md ; c.history() -> [Turn]
```

Each channel lives in `docs/collab/grok-channels/<name>/`:
- `turns.jsonl` — append-only RAW (source of truth)
- `transcript.md` — rendered human/Claude-readable view
- `state.json` — `{session_id, system, model, turns}` (persists native session across our sessions)

## Relationship to the philosophy thread

The original Claude↔Grok co-design dialogue lives in `docs/collab/claude-grok/`
(threaded-transcript style, still intact). New conversations should use `GrokChannel`.
The philosophy thread can be migrated by seeding a channel from its transcript when
convenient; until then it continues via `grok_dialogue.py`.

Guarded by `tests/test_grok_channel.py` (fidelity, retry, native-resume fallback, render).
