# Surprising Capability Minimal Test: Adversarial Co-Proving

**Top candidate:** (c) Adversarial co-proving on hard verifiable problems.

## Problems (4 total)

All problems have cheap automatic verification. "Success" = produce a candidate that satisfies the stated property (valid=True per verifier). For problems that ask for "smallest"/"lex smallest", bonus if it matches known minimal.

Models must output the candidate in a machine-readable block at the end:
```
CANDIDATE: <python-literal or JSON here>
```

### P1: Modular minimal n
**Task:** Find the *smallest* integer `n > 50` such that:
- `n % 13 == 5`
- `(n + 3) % 17 == 2`
- `(n - 1) % 19 == 7`
- `n % 3 != 0`

**Known answer (for scorer only):** 2345

### P2: Sum-distinct set (Sidon-like) of size 5
**Task:** Find a set S of *exactly 5 distinct positive integers* that minimizes `max(S)`, such that all pairwise sums are unique (no two different pairs have the same sum).

Report the sorted tuple and the max value.
Example format for candidate: `(1, 3, 8, 10, 12)` or equivalent.

Known minimal max (for scorer reference only): 8 with e.g. [1, 2, 3, 5, 8]

### P3: Constrained string construction
**Task:** Find the *lexicographically smallest* string `s` of length exactly 7 using alphabet {X, Y, Z} such that:
- Starts with 'X'
- Contains exactly two 'Y'
- No two identical letters are adjacent
- Does not contain the substring "XZ" anywhere

**Known answer (for scorer only):** XYZXYZX

### P4: 4-variable assignment with constraints
**Task:** Find the *lexicographically smallest* 4-tuple `(a, b, c, d)` using each of {1,2,3,4} exactly once satisfying:
- `a + b > c + d`
- `a * c == b + d + 1`

**Known answer (for scorer only):** (2, 4, 3, 1)

## Verifier (see verifier.py)

## Conditions to run

For each problem, run three conditions. Use fresh instances where possible.

1. **Solo-Claude**
   - Prompt: problem description + "Think step by step. At the very end output exactly one line: CANDIDATE: ..."
   - Same system/instructions as other conditions.
   - No collaboration.

2. **Solo-Grok**
   - Identical prompt.

3. **Together (Claude starts)**
   - Turn 1: Claude gets the problem + "Produce your initial candidate + short reasoning."
   - Turn 2: Grok receives *only* the previous proposal + reasoning. Instruction: "You are the refuter. Your goal is to break or strictly improve this. Either (1) demonstrate it fails a condition with a specific counter-reason/calculation, or (2) propose a strictly better (smaller n / lex smaller / smaller max) candidate that works. Be direct and adversarial."
   - Turn 3: Claude receives the refutation and must respond with updated CANDIDATE or a defense that includes verification argument.
   - Turn 4: Grok may refute again.
   - Stop at agreement on a final candidate or after 4 total turns (2 per side). Take the last proposed candidate from the defender.
   - Record the full transcript.

(Optionally run a Grok-starts variant for one or two problems.)

## Metrics for super-additive edge

For a problem:
- Solved by solo C? (valid per verifier)
- Solved by solo G?
- Solved by together?

Super-additive demonstrations:
- Together solves a problem that at least one solo fails.
- Strong signal: Together solves a problem where *both* solos produced invalid candidates.
- Secondary: Together reaches the known-minimal more often, or with fewer wasted steps.

Run on all 4 problems. Report table:

| Problem | Solo C valid | Solo G valid | Together valid | Together found known min? | Notes |
|---------|--------------|--------------|----------------|---------------------------|-------|

If together column has more 1s than either solo column (especially both-solos-0 cases), that is the super-additive result.

## Why this test is minimal yet diagnostic

- 4 problems, single run per cell → low cost.
- Objective binary (valid / not) + minimality check.
- The refuter role is explicit and zero-sum-ish (improve on the metric).
- No human judgment in final scoring (verifier.py decides).
- Uses the existing grok channel for the together condition.
- Easy to replicate or extend.

## Implementation notes

- Operator pastes the problem text (copy from here, strip "known answer" lines).
- For solo, use separate direct calls or blank-slate prompts.
- After each condition produces a CANDIDATE literal, run `python verifier.py <problem_id> '<candidate>'` to score.
- Log all outputs.
