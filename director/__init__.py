"""Director 2.0 — persistent recursive AI symbiont orchestration framework.

Two loops, one spine:

* The **command loop** (from Director 1.0): a strategic Director agent maintains a
  project charter, modules, a task graph, and durable event-sourced state. It
  dispatches bounded task packets to specialized subagents and — at meaningful
  branch points — surfaces **Command Packets** to the human: consequential
  choices with tradeoffs, not approval forms.

* The **discovery loop** (from the Recursive Discovery Engine): a
  Builder/Adversary/Synthesizer cycle that proposes candidate solutions, grounds
  them in an isolated sandbox against trusted oracles, scores them with
  trusted code (never self-reported), tracks novelty, and records verdicts with
  declared semantics.

Constitution (non-negotiable design rules, inherited from RDE v11):

1. **Grounding first** — no claim about generated code/work is believed until it
   has been executed or deterministically verified.
2. **Correctness decoupling** — the model that generates never grades itself.
   Verification is trusted Python or a different model with problems-only context.
3. **Problems, not rubrics** — feedback to generators carries failing cases and
   causal diagnoses, never thresholds, scoring weights, or worked idioms.
4. **Declared semantics** — every verdict flag (pass/beats/matches/below) is
   computed by a declared, recorded rule; fragile results are labeled fragile.
5. **Human command at branch points** — consequential decisions surface as
   Command Packets. Autonomy is bounded by policy, never assumed.
"""

__version__ = "2.0.0"
