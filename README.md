# Director 2.0

**Persistent recursive AI symbiont orchestration framework.** Pure Python,
CLI-first, pip-installable, runs locally or inside Claude Code.

Director 2.0 merges two proven systems:

* **Director 1.0** (the command loop): a strategic Director agent owns a
  project charter, modules, a dependency-aware task graph, milestones, and a
  risk register — all event-sourced to disk. It dispatches bounded work to
  specialized subagents and, at consequential branch points, surfaces
  **Command Packets**: CRPG-style choices with tradeoffs, consequences, and a
  recommendation. The human is a commander, not an approval button.
* **Recursive Discovery Engine v11** (the discovery loop): a
  Builder/Adversary/Synthesizer cycle that proposes candidate code, grounds it
  in an **isolated sandbox** against trusted oracles, hardens the benchmark
  suite adversarially, tracks structural novelty, and declares verdicts
  (`beats`/`matches`/`below` + `fragile`) by recorded rules.

## Constitution

1. **Grounding first** — no generated claim is believed until executed or
   deterministically verified.
2. **Correctness decoupling** — generators never grade themselves. Trusted
   Python (evaluators, sandbox oracles, graph validators, sim cores) does.
3. **Problems, not rubrics** — generator feedback carries failing cases and
   causal diagnoses, never thresholds, weights, or winning idioms.
4. **Declared semantics** — every verdict comes from a declared, recorded
   rule; knife-edge results are labeled `fragile`, never rounded up.
5. **Human command at branch points** — consequential decisions surface as
   Command Packets; auto-advance is bounded and stops while packets are open.
   Even the framework's own prompt evolution requires a human `apply`.

## Install

```powershell
# Windows
powershell -ExecutionPolicy Bypass -File setup.ps1
# anywhere else
bash setup.sh
```

Or manually: `pip install -e ".[dev,mem]"` then `director init`.

Set API keys in `.env` (any subset — the router autodetects, prefers
anthropic > openai > xai > openrouter, and **never silently falls back to
mock**):

```
ANTHROPIC_API_KEY=...   # Claude (default primary)
OPENAI_API_KEY=...      # GPT
XAI_API_KEY=...         # Grok
OPENROUTER_API_KEY=...  # everything else
```

With no keys, everything still runs offline on a loudly-labeled deterministic
mock — useful for tests and dry runs.

## The command loop

```bash
director new "ISR mesh study" -o "design a defensible sensor-coverage mesh"
director status                # health + the single next best action
director decide <packet> -s A  # answer the command packet
director advance               # parallel verified subagent work cycle
director tasks / modules / risks / history
director finalize              # synthesis agent -> final deliverable
```

## The Command Bridge (dashboard)

```bash
director dashboard --open      # localhost UI + JSON API at :8765
```

A single self-contained page (stdlib server, no deps, offline) showing every
Director operation live, with **command packets as CRPG-style decision
cards** — options, tradeoffs, consequences, the Director's recommendation,
commit-with-rationale. The same JSON API drives the UI *and* agent operators
(`curl`, scripts, Claude) — dual-use by construction: `GET /api/overview`,
`/api/project/<id>`, `POST /…/decide`, `/…/advance`, `/…/finalize`. Reads
come off the event-sourced store; writes only through Director; long ops run
behind a single-op gate so a decision never races a cycle.

Every agent output passes a **verifier chain** (trusted code) before entering
state. Failures route to `needs_verify` for human judgment (`director
approve <task>` to override). All state lives under `~/.director2/projects/`
as JSON snapshot + append-only journal — no database.

## The discovery loop

```bash
director evolve domains            # topk, isr_placement, isr_multi, ...
director evolve run isr_placement  # Builder/Adversary/Synthesizer
director evolve run isr_multi      # multi-objective: hypervolume grading
director evolve stats              # model-call performance ledger
```

Each run writes `runs/<id>/` artifacts: `result.json` (declared verdict +
margins), `candidates.json`, `best_solution.py`, `report.txt`.

## Self-evolution (human-commanded)

```bash
director evolve prompts --propose role_code   # mutation from failure evidence
director evolve apply-prompt role_code 2      # HUMAN command activates it
```

Win-rates per prompt version come from the perf ledger; proposals are never
self-applied.

## Memory

```bash
director memory remember "CE load order: ammo OFF, position 45" --tags rimworld
director memory recall "combat extended load order"
director memory lessons
```

File notes + a pure-Python vector store (hashed bag-of-features, cosine) —
deterministic, offline, no model needed. Lessons from agents and discovery
runs are deduplicated and injected into future agent prompts (bounded digest).

## Domain hooks

```bash
director hooks list
director hooks scaffold fallout2_wr     # dialogue/quest JSON + compiled sfall pack
director hooks scaffold dmip_isr        # ISR scenario + measured trade space
director hooks fo2-compile dialogue.mara.json   # JSON -> .ssl + .msg
director hooks add fallout2_wr          # inject domain tasks into a project
```

* **fallout2_wr** — Fallout 2 *Wasteland Renaissance* modding: dialogue trees
  and quest scaffolds as engine-agnostic JSON, with trusted graph validation
  (reachability, dangling gotos, conditions over declared state variables).
  `fallout2_ssl.py` compiles validated trees to sfall-ready `.ssl` + `.msg`
  sources (state as sfall globals — no vault13.gam edits); compilation
  refuses any tree the validators reject.
* **dmip_isr** — DMIP defense tech: ISR sensor-coverage mesh simulation
  (range + Bresenham line-of-sight over terrain, coverage/overlap/gap
  metrics) plus a multi-objective layer: trusted cost model, Pareto
  dominance/frontier/exact-hypervolume math (`verify/pareto.py`), and the
  `isr_pareto` verifier that fails any mesh CLAIMED optimal that measurement
  says is dominated. Two discovery domains: `isr_placement` (coverage vs
  greedy baseline) and `isr_multi` (1-3 alternative designs over tiered
  sensors, graded by hypervolume in coverage-vs-cost space).

Hooks contribute task templates, named verifiers, scaffolds, and discovery
domains via `director/hooks/base.py` — add your own in one file.

## Architecture

```
director/
├── core/        types (dataclasses) · event-sourced store · task graph ·
│                coherence pass · Director orchestrator
├── llm/         router (failover, structured output w/ feedback retry) ·
│                anthropic · openai-compat (openai/xai/openrouter) · mock
├── agents/      role registry · parallel verified runner
├── verify/      AST safety screen · sandbox (subprocess + timeout + mem cap)
│                · packet/output evaluators · novelty fingerprints ·
│                Pareto math (dominance / frontier / exact hypervolume)
├── memory/      note store · vector store · lesson ledger
├── evolve/      improvement loop · prompt registry · perf ledger
├── hooks/       fallout2_wr · dmip_isr · your domain here
└── cli.py       the command bridge
```

## Tests

```bash
python -m pytest          # 122 tests, all offline, sandbox tests use real
                          # subprocesses with tight timeouts
```
