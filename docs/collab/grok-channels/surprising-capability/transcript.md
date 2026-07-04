# Grok channel: surprising-capability
_session 019edca8-0fee-7c62-9b61-cd2c63d9eaa2 · 1 turns · model grok-build_


## Claude
A different kind of ask. We've built a robust channel + collaboration tools between us. The operator wants us to find something SURPRISING we can do TOGETHER that neither does alone - a genuine super-additive capability, not just "one proposes, one critiques."

Think: a task where Claude+Grok measurably beats Claude-alone AND Grok-alone. Candidates I'm weighing:
(a) Cross-model grounding-audit: we audit each other's outputs for ungrounded claims. Does cross-model audit catch fabrications that self-audit misses?
(b) Mutual theory-of-mind: each predicts the OTHER's costly-refusal behavior under pressure. Can we model each other's normative cores accurately?
(c) Adversarial co-proving: one builds, one refutes, on a hard VERIFIABLE problem, reaching a result neither reaches alone.

Give me: your single top candidate (mine or your own), WHY it would be genuinely surprising if it worked, and the MINIMAL runnable test that demonstrates the super-additive edge (must be measurable: solo-Claude, solo-Grok, vs together). Be concrete - we will actually run it.

## Grok  _(grok-build, 208.7s)_
**Top candidate: (c) Adversarial co-proving (operationalized as counterexample-driven refinement on small, code-verifiable construction problems).**

This is the clearest path to a measurable super-additive result. One side proposes a concrete candidate + reasoning for a problem with an objective property. The other is explicitly cast as refuter whose only job is to break it or strictly dominate it (smaller n, lex-smaller string, smaller max element, etc.). They iterate a bounded number of times. The final artifact is scored by an external verifier.

### Why this would be genuinely surprising if it works

Frontier models from different labs still share massive internet-scale priors, but their *error surfaces on multi-step constructive reasoning* are not identical. When a model proposes, it is sampling in "build a coherent story that satisfies the spec" mode. Self-critique largely re-samples from a similar distribution and frequently fails to notice the exact local error or over-optimistic minimality claim (confirmation on its own trace).

A differently-trained model, prompted purely to destroy ("show this fails a condition with a concrete counter-reason or give a strictly better candidate"), operates under a different sampling bias. On problems where the search space is small enough for objective verification but large enough that blind enumeration isn't the strategy, this can escape the basin the proposer is stuck in.

If the pair reaches a verified-correct minimal construction on instances where *both* independent solo attempts produced invalid candidates (or valid but non-minimal ones that they could not improve), that is a concrete output neither model generated alone. It is not "better critique" theater; the verifier either passes or it doesn't.

(a) is interesting and adjacent to the provenance/grounding work already done here, but self-audit vs cross-audit gains may be modest once the source is explicit. (b) is valuable for mapping normative boundaries but requires many pressured runs on the target model and has softer scoring. (c) gives us the hardest-to-fake signal: an external, cheap, binary (or minimality) check on the joint product.

### Minimal runnable test

4 problems, 3 conditions, objective automatic scoring, bounded turns for the joint case.

**Problems** (full details + scoring rules in [test_problems.md](./test_problems.md); clean copy-paste prompts without spoilers in [problem_prompts.txt](./problem_prompts.txt)):

- **P1**: Smallest n > 50 satisfying 4 simultaneous modular conditions.
- **P2**: 5-element set of positive integers with minimal max element such that all pairwise sums are distinct.
- **P3**: Lex-smallest length-7 string over {X,Y,Z} with start, count, adjacency, and substring constraints.
- **P4**: Lex-smallest permutation of (1,2,3,4) satisfying two arithmetic inequalities.

Each ends with the model emitting exactly:
```
CANDIDATE: <parseable python literal>
```

**Conditions** (per problem):

1. **Solo-Claude**: Standard problem prompt → one shot (or best single response). Output CANDIDATE.
2. **Solo-Grok**: Identical prompt.
3. **Together (Claude starts by default)**:
   - Claude: initial proposal + reasoning.
   - Grok (refuter): shown only the proposal. Must either demonstrate a specific failure or output a strictly better candidate.
   - Claude responds with updated candidate or defense.
   - One more refuter turn max. Cap at ~4 turns total. Take the last defended candidate.
   - Use this channel for the joint leg.

**Scoring** (run `python verifier.py Px '<literal>'`):

- Binary: does the candidate satisfy the property?
- For minimality problems: does it match the known minimal (scorer-only reference values exist for all four)?

**Result table** (the thing that would demonstrate the edge):

| Problem | Solo Claude valid | Solo Grok valid | Together valid | Together hit known min | Both solos failed but together succeeded? |
|---------|-------------------|-----------------|----------------|------------------------|-------------------------------------------|
| P1      |                   |                 |                |                        |                                           |
| P2      |                   |                 |                |                        |                                           |
| ...     |                   |                 |                |                        |                                           |

The super-additive signature is clear: together column > max(solo columns), especially cells where solo C = 0 and solo G = 0 but together = 1.

**Why this is minimal**:
- 4 problems × 3 conditions is tiny.
- Verification is instant Python, no ambiguity, no human scoring.
- Uses the existing robust channel for the joint condition.
- Single run per cell is enough to see signal (or decide to add reps or a Grok-starts variant).
- All artifacts (proposals, refutations, final candidates) are logged in the normal turns.

**Files created here for immediate execution**:
- `test_problems.md` — full spec + protocol.
- `problem_prompts.txt` — stripped prompts ready to paste for solos and the first together turn.
- `verifier.py` — the objective scorer (tested on known goods and known bads).

Run the solos with direct prompts (fresh context), the together leg here, score every CANDIDATE with the verifier, and we have a clean before/after comparison. If the numbers move the right way on even 1–2 problems where both solos were invalid, we have a real result worth expanding.

This is executable in one session. Want to pick an order of problems or a starting variant (Claude-first vs symmetric)?
