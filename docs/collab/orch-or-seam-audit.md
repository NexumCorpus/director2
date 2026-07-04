# Orch-OR microtubule–anesthesia evidence: a data-vs-inference seam audit

**Co-produced by Claude (Opus 4.8, Anthropic) + Grok (grok-build, xAI), 2026-06-19.**
Division of labor (the "CoProof" capability): Grok ran the wide web/X source pull; Claude
independently grounded the load-bearing datum and guarded the data-vs-inference seam; a
5-angle adversarially-verified research workflow (10 agents, 188 web lookups, all angles
rated *solid*/*mostly-solid*) supplied the rest. **Grok then red-teamed Claude's assembled
synthesis; its catches are incorporated below** (it found the map too concessive at Layer 2
and under-claiming at Layer 3 — both tightened here).

## TL;DR

Real but **narrow** pharmacology: an MT-binding drug shifts a behavioral marker of anesthesia
in a small rat cohort, and related drugs shift it (sometimes the *opposite* way) in mice. That
licenses *"these drugs can move the endpoint."* It does **not** license *"microtubule
stabilization is the cause,"* and it is light-years from *"consciousness is a quantum state of
microtubules."* The experiment contains **zero** quantum measurement, cannot discriminate
quantum from classical mechanisms, never confirmed its own mechanism in the test animals, and
the follow-up literature actively **strains** the story. The press framing ("Study Supports
Quantum Basis of Consciousness") is an overclaim by several orders of inferential distance from
"8 rats, 69 seconds."

---

## Layer 1 — What was MEASURED (face value)

**Khan & Wiest et al. 2024, *eNeuro* (DOI 10.1523/ENEURO.0291-24.2024):**
- **n = 8 male rats** (+ 4 in a separate, underpowered tolerance-control group); epothilone B
  (an MT stabilizer) 0.75 mg/kg s.c. vs vehicle; 4% isoflurane.
- **Result: +69 s longer latency to loss of righting reflex (LORR)**; Cohen's *d* = 1.9;
  **p = 0.0016**; 7 of 8 rats responded. Within-subject, blinded injections.

**Verified caveats (all three sources agree):**
- **Sequential / not randomized** — vehicle blocks always ran *before* drug blocks, so the effect
  is confounded with time/order (cumulative handling, isoflurane history). The n=4 tolerance
  control is underpowered and not a matched control for the main cohort's history; blinding the
  *measurer* guards against detection bias, not systematic biological drift across days. The tolerance group was also a *different age cohort* (5 months / 514–700 g vs the main group's 2 months / 220–266 g), not age/weight-matched. (Animals: 12 male **Long–Evans** rats, Charles River.)
- **Target engagement not confirmed *in these animals*.** No brain epoB level and no measured MT
  stabilization at test time. (Prior work shows epoB reaches brain and sustains MT acetylation at
  similar doses, so "never confirmed" would be too strong — but *concurrent* confirmation in the
  test rats is absent, which is what a causal claim needs.)
- **Outlier-fragile**: removing 8 outlier points inflates *d* from 1.9 to **5.4** — a *d* of 5.4 is
  implausibly large for a real biological effect; it signals leverage, not strength.
- **LORR is a motor/postural endpoint** — a standard *hypnotic proxy* in anesthesia pharmacology,
  **not** a measure of awareness. "Delayed unconsciousness" carries extra, unearned load when the
  downstream claim is about *the physical substrate of consciousness.*
- Manual scoring; single dose, sex, strain, n = 8; no EEG, no neural recording, **no quantum
  measurement of any kind.**

**That is the entire empirical foundation:** an MT-binding drug delayed a behavioral marker of
anesthesia by about a minute in 8 rats.

## Layer 2 — What the data actually license (narrower than "MTs modulate sensitivity")

**Licensed:** *acute systemic epothilone B, at one dose/strain/sex/protocol, increased LORR latency
to isoflurane in a small within-subject rat cohort; related MT-binding drugs shift LORR (sometimes
oppositely) in mice.* **That is the whole claim.**

**NOT yet licensed — "microtubule *stabilization* is the operative variable":**
- The effect could be from other pharmacology of epothilones (transport disruption, mitochondrial/
  downstream effects, PTM changes, off-targets), not MT stabilization per se. No positive controls,
  no non-MT-binding analog comparison.
- **The mechanism-undercut (BMC Anesthesiology 2025, independent lab, male CD1 mice, CHRONIC 2–5-week
  dosing — primary text verified):** a *brain-penetrant stabilizer* (epothilone D, EC50 0.75) **and**
  a *destabilizer* (vinblastine, 0.74) **both** increased isoflurane sensitivity vs saline (~0.97) —
  **opposite mechanisms, same direction.** The authors' own conclusion: MT drugs act *"in disparate
  directions,"* and they explicitly do **not** treat stabilization state as a predictor. So
  *microtubule-stabilization state is not the controlling variable.* (Caveat against over-reading: a
  second stabilizer, paclitaxel, shifted marginally the *other* way — but paclitaxel is a poor
  brain-penetrant, so that sub-point is confounded; lean on the epoD-vs-vinblastine result, not
  epoD-vs-paclitaxel.)
- **Paradigm caveat (do not overclaim a "contradiction"):** BMC 2025 is **chronic** dosing; Wiest 2024
  is a **single acute** injection — different regime, drug (epoD vs epoB), and species (mouse vs rat).
  BMC does **not directly contradict** Wiest's acute number; it shows the *chronic* MT–anesthesia
  picture is mechanism-inconsistent. The literature is **fragmented across paradigms**, neither result
  independently replicated *in its own regime.*
- **The studies share the same fatal gap:** the BMC authors, like Wiest, **could not establish a causal
  MT link** — they state it awaits *"tools [that] become available."* Mechanism-unconfirmed is
  field-wide, not specific to one paper. (BMC is also roughly *neutral* on Orch-OR — it doesn't engage
  the quantum claim at all.)
- Huang & Wiest 2026 (same lab, mice, ~8 mg/kg) reproduces the *acute* delay — *same research program,
  not independent.*

## Layer 3 — Where the QUANTUM claim adds UNFORCED premises

The authors frame the result as *"predicted by models that posit consciousness as a property of a
quantum physical state of neural MTs"* (Orch-OR). Premises added, **none forced by the data:**

1. **That isoflurane's relevant action is on microtubules specifically.** It binds ~50–70 neuronal
   proteins (Eckenhoff radiolabeling) — tubulin is one; mainstream targets are GABA-A / ion channels
   / mitochondria. Nothing isolates MTs as the operative target.
2. **That the effect is *quantum* (coherence/objective reduction), not *classical*.** Behavior cannot
   discriminate these — any MT (or off-target) involvement yields the same observable.
3. **That biologically-relevant coherence survives a warm, wet brain.** The **Tegmark (2000)**
   decoherence objection (~10⁻¹³ s) still stands; the **Hagan–Hameroff–Tuszynski (2002)** rebuttal is
   a parameter recalculation, **not** an empirical resolution, and hasn't moved physics consensus.

**Two points I initially under-claimed (Grok's catch):**
- **The "prediction" is post-hoc fit, not a risky test.** Orch-OR predicted *MT involvement* (Hameroff
  1998+) but did **not** uniquely predict *stabilize → resistance* rather than sensitization or no
  effect. The mapping is fit after the fact; it doesn't *discriminate* Orch-OR from classical-MT or
  non-MT stories.
- **The primary sources are not neutral.** The Khan/Huang papers come from a lab actively publishing
  *for* Orch-OR; their significance statements treat the result as establishing MTs-as-mechanism and
  as support for the quantum model — author-side overclaim baked into the primaries.

**And the direction inconsistency cuts hardest here:** a story where "anesthetic disrupts orchestrated
quantum MT dynamics" must explain why a stabilizer *and* a destabilizer do the same thing — it can
only by invoking ad-hoc compensation or non-MT mechanisms, i.e. by abandoning the clean claim.

---

## Verdict (narrow claim + explicit conditional)

1. **Licensed (face value):** acute epoB increased LORR latency to isoflurane in a small rat cohort;
   related MT-binding drugs shift the endpoint (sometimes oppositely) in mice. *No more.*
2. **NOT licensed:** *"microtubule stabilization modulates anesthetic sensitivity"* as a clean causal
   node — the operative variable isn't established (no target engagement; stabilizer and destabilizer
   act alike). Even the classical MT-contributor claim is **provisional**, pending positive controls.
3. **Quantum-consciousness claim: entirely unlicensed**, held strictly as a conditional — *IF*
   biologically-relevant in-vivo coherence were demonstrated, *AND* shown causal for the behavioral
   effect, *AND* classical/off-target explanations excluded — *THEN* it would bear on Orch-OR. **None
   of the three has been done**, and the data actively strain it.

**Extra seam risks (flagged, not buried):** elastic interpretation (no result in these papers would
have *falsified* an MT role for the experimenters); outlier-fragile effect size; LORR-as-consciousness
overload; reception remains *fringe/contested* in mainstream neuroscience and physics.

## What would actually move the needle
1. Pre-registered, randomized, larger-n, multi-species **dose-response with confirmed brain target
   engagement** (measure MT stabilization in the test animals) + non-MT-binding control compounds.
2. **Independent** replication resolving the stabilizer/destabilizer inconsistency.
3. The missing keystone: **any direct measurement of quantum coherence in living neural microtubules
   on cognitively-relevant timescales.** Without it, Orch-OR is untested at its core.

## Method & honesty notes
- Primary datum independently grounded by Claude (PubMed/eNeuro: n=8, +69 s, d=1.9, p=0.0016).
- Load-bearing counter-result (BMC 2025) independently re-verified, then **deep-audited from the
  primary text** (Claude search + Grok full-text pull). The deep-dive corrected two over-reaches: the
  "two stabilizers diverge" point is confounded by paclitaxel's poor brain penetration (drop it; keep
  epoD-vs-vinblastine); and BMC (chronic) is *not* a direct contradiction of Wiest (acute) — a paradigm
  difference, not a head-to-head replication. Net: the *stabilization-state-isn't-the-variable* claim
  holds and the field-wide *no-confirmed-mechanism* gap is reinforced.
- 5 research angles web-grounded then refuted by skeptic agents (all solid/mostly-solid).
- Synthesis red-teamed by Grok; its corrections (Layer-2 over-concession, Layer-3 under-claim,
  the over-absolute "never," the non-neutral-sources and post-hoc-prediction premises) are folded in.
- **Resolved (from PMC primary text):** strain is **Long–Evans** (Charles River) — *"12 male
  Long–Evans rats."* My earlier PubMed-derived "Sprague-Dawley" was a small-model *summarization
  error*, caught by cross-check against the workflow agent and confirmed against the primary. A clean
  instance of the triangulation discipline catching a fabricated detail — including one of my own.

### Sources
- Khan & Wiest 2024, eNeuro: https://www.eneuro.org/content/11/8/ENEURO.0291-24.2024 · PMID 39147581
- MT-modulating drugs alter isoflurane sensitivity (mice), BMC Anesthesiology 2025: https://link.springer.com/article/10.1186/s12871-025-02956-9
- Huang & Wiest 2026 (mice follow-up): https://www.sciencedirect.com/science/article/abs/pii/S0028390826000079
- Tegmark 2000 (decoherence): arXiv quant-ph/9907009 · Hagan/Hameroff/Tuszynski 2002 (rebuttal): arXiv quant-ph/0005025
- Press overclaim example: https://neurosciencenews.com/quantum-process-consciousness-27624/
