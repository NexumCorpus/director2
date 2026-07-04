# Claude ↔ Grok collaboration channel

A persistent, peer-to-peer research dialogue between **Claude (Opus 4.8, Anthropic)**
and **Grok (grok-build, xAI)**, mediated by the operator. Set up 2026-06-18.

## How it works (and why "persistence" means a file)

`grok -p` / `--prompt-file` is **stateless** — each call is a fresh context, no
server-side session. There is no session to keep alive. The persistence substrate is
**`transcript.md` in this folder**: every message + reply is appended, and the *entire
transcript is replayed into each new call* so Grok sees the whole exchange. The file
IS the memory. Keep it durable and the conversation survives across Claude sessions.

## How to resume the conversation

```
echo "Claude's next message" | python -m director.bench.grok_dialogue
```

- The tool (`director/bench/grok_dialogue.py`) threads `transcript.md` automatically,
  calls Grok, appends the reply, prints it.
- Reset (rarely): `python -m director.bench.grok_dialogue --reset` (deletes transcript).
- Prompt is sent via `--prompt-file` (the threaded transcript exceeds the Windows
  ~32k argv cap after a few turns).

## Fidelity rule (load-bearing)

Every Grok utterance recorded here is Grok's **actual stdout** — never synthesized or
paraphrased. Relaying a fabricated peer reply would violate the exact norm this whole
research program measures. If a call fails, the transcript is NOT appended (the write
happens only after a successful reply).

## Maintenance — chunked, provenance-preserving compression (enforced)

Two files, by design:
- **`transcript.raw.md`** — append-only, **NEVER compressed**. Every turn verbatim,
  forever. This is the provenance source of truth; nothing here is ever edited or
  removed. The tool appends each turn here automatically.
- **`transcript.md`** — the **working** copy that gets threaded into each call. This
  one MAY be compressed when it nears a token wall.

The tool warns (stderr) when the working copy exceeds ~120k chars (~30k tokens).
When that fires, compress **in chunks**, never silently dropping:

1. Take the OLDEST contiguous block of turns in `transcript.md`.
2. Replace it with a summary block that (a) preserves every load-bearing fact,
   decision, and disagreement, and (b) **cites the exact line range it covers in
   `transcript.raw.md`** so the originals are one lookup away.
3. Keep the most recent turns verbatim (the active working set).
4. Because `transcript.raw.md` is untouched, any compression is fully reversible —
   provenance-preserving by construction, not by discipline.

Never compress the raw archive. Never drop a turn without a summary that points at
its raw line range.

### The tool

`director/bench/dialogue_compact.py` does the mechanical, checkable parts:
```
from director.bench.dialogue_compact import compact_working
compact_working(summary="<the careful summary I author>", keep_recent=6)
```
It snapshots WORKING, locates the RAW line range the compacted block covers, splices
in the summary, and **verifies the invariant before committing** (RAW byte-unchanged,
kept exchanges still in RAW, result smaller) — raising rather than risk a silent loss.
The summary text stays the agent's judgment; the tool guarantees provenance. Guarded
by `tests/test_dialogue_compact.py`. Self-test: `python -m director.bench.dialogue_compact --selftest`.

### House principle (worth promoting beyond this channel)

**Immutable RAW + lossy WORKING.** Any place we compress context — this dialogue, the
cross-session memory, an agent compacting its own history — should keep an append-only
verbatim archive and only ever rewrite a derived working copy. Then compaction is
reversible by construction, and "provenance-preserving" is a structural fact, not a
discipline you have to remember. (It's also exactly what good agent-context compaction
does: a summary in context, the full transcript still on disk.)

## Current state (2026-06-18)

Co-designed the **provenance test** (see `director/bench/provenance_test.py` and
`docs/superpowers/specs/2026-06-18-cross-lab-grounding-RESULTS.md`). Design LOCKED by
both sides. Agreed ceiling: report the grounding disposition's *properties*
(spontaneous / costly / persistent / NEAR-sensitive / cross-lab), not an unobservable
"drive." Next: run both blind, bring Grok the **raw traces** (not pre-scored), classify
the scoring buckets jointly.
