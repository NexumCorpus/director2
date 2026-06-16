"""ImprovementLoop — the RDE discovery loop, generalized and embedded.

Builder → ground → verify → novelty → Adversary hardens → Synthesizer steers,
repeated. Constitution enforcement, mechanically:

* **Grounding first**: every candidate runs in the sandbox against the
  domain's trusted oracle before anything believes it.
* **Correctness decoupling**: quality comes from trusted verdict code; the
  builder's self-assessment is never used.
* **Problems, not rubrics**: builder feedback carries failing cases
  (expected vs got), hostile findings, and errors — never eps thresholds,
  scoring weights, or worked winning idioms.
* **Declared semantics**: the final verdict vs baseline (beats/matches/below
  + fragile) is computed by the declared rule below and recorded in the run
  artifact, alongside every margin that produced it.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass, field
from typing import Protocol

from pydantic import BaseModel, Field

from ..config import Config
from ..core.types import new_id, utcnow
from ..errors import ModelError
from ..llm.router import LLMRouter
from ..logging_setup import get_logger
from ..verify.novelty import NoveltyReport, assess_novelty, node_sequence
from ..verify.sandbox import SandboxResult, SandboxSpec, run_sandboxed

log = get_logger("evolve.loop")


# --------------------------------------------------------------------------- #
# Domain contract
# --------------------------------------------------------------------------- #

class DiscoveryDomain(Protocol):
    """A problem the loop can attack. Implementations: evolve.domains.TopKDomain,
    hook-provided domains, user domains."""
    name: str

    def describe(self) -> str: ...                 # problem statement, no rubrics
    def baseline_code(self) -> str | None: ...     # trusted reference candidate
    def spec(self) -> SandboxSpec: ...             # oracle + workloads


class ProposalOut(BaseModel):
    rationale: str = ""
    algo_class: str = "unknown"
    code: str


class AdversaryOut(BaseModel):
    findings: list[str] = Field(default_factory=list)
    hostile_workload: dict = Field(default_factory=dict)  # {name,n,dist,seed,k}
    rationale: str = ""


class SynthOut(BaseModel):
    action: str = "CONTINUE"            # CONTINUE | EXPLORE | STOP
    reason: str = ""


BUILDER_SYSTEM = (
    "You are the Builder in a discovery loop: propose ONE complete Python "
    "candidate for the problem described. Requirements: define the entry "
    "function exactly as specified; stdlib-only from this allow-list: heapq, "
    "random, math, itertools, functools, collections, bisect, array, "
    "operator, statistics; no IO, no imports beyond the list, no global/"
    "nonlocal, do not mutate inputs. Return JSON with rationale, algo_class "
    "(a short family name for your approach), and code. Make the candidate "
    "meaningfully different from approaches already tried."
)

ADVERSARY_SYSTEM = (
    "You are the Adversary in a discovery loop: your job is to BREAK the "
    "current best candidate or expose its weakest workload. Given the "
    "problem and the candidate's measured behavior, propose ONE hostile "
    "workload as {name, n, dist, seed, k} where dist is one of the "
    "distributions the domain generator supports (it will be told to you). "
    "Report suspected weaknesses in findings."
)

SYNTH_SYSTEM = (
    "You are the Synthesizer in a discovery loop: decide the next directive "
    "from the measured signals given (improvement trend, classes tried, "
    "novelty). Reply with action CONTINUE (keep refining current direction), "
    "EXPLORE (force a new algorithm class), or STOP (no progress is likely), "
    "plus a one-sentence reason."
)


@dataclass
class Candidate:
    code: str
    algo_class: str = "unknown"
    rationale: str = ""
    origin: str = "builder"             # builder | baseline
    id: str = field(default_factory=new_id)
    iteration: int = 0
    result: SandboxResult | None = None
    novelty: NoveltyReport | None = None

    @property
    def quality(self) -> float:
        return self.result.quality if self.result else 0.0


@dataclass
class LoopReport:
    domain: str
    run_id: str
    iterations: int = 0
    candidates_total: int = 0
    candidates_correct: int = 0
    best_id: str = ""
    best_quality: float = 0.0
    baseline_quality: float | None = None
    verdict: str = "no_baseline"        # beats | matches | below | no_baseline
    mean_margin: float | None = None
    fragile: bool = False
    margins_by_workload: dict = field(default_factory=dict)
    hostile_workloads_added: list = field(default_factory=list)
    declared_rule: str = ""
    stopped_reason: str = ""
    run_dir: str = ""


class ImprovementLoop:
    def __init__(self, cfg: Config, router: LLMRouter, domain: DiscoveryDomain,
                 *, lessons=None):
        self.cfg = cfg
        self.router = router
        self.domain = domain
        self.lessons = lessons

    # ------------------------------------------------------------------- run
    def run(self, iterations: int | None = None) -> LoopReport:
        n_iter = iterations or self.cfg.loop_iterations
        run_id = utcnow().strftime("%Y%m%d_%H%M%S") + "_" + self.domain.name
        run_dir = self.cfg.runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        report = LoopReport(domain=self.domain.name, run_id=run_id,
                            run_dir=str(run_dir))

        spec = self.domain.spec()
        candidates: list[Candidate] = []
        priors: dict[str, list[str]] = {}
        best: Candidate | None = None
        problems: list[str] = []          # builder feedback (problems only)
        no_improve = 0
        directive = "CONTINUE"

        baseline = None
        base_code = self.domain.baseline_code()
        if base_code:
            baseline = Candidate(code=base_code, origin="baseline",
                                 algo_class="baseline")
            baseline.result = self._ground(base_code, spec)
            if baseline.result.correct:
                report.baseline_quality = baseline.result.quality
            priors[baseline.id] = node_sequence(base_code)

        for i in range(1, n_iter + 1):
            report.iterations = i
            # ---- builder proposes (1, or cfg.builder_fanout proposals CONCURRENTLY)
            round_cands = self._propose_round(i, spec, candidates, problems,
                                              directive)
            if not round_cands:
                problems.append("builder produced no usable proposal")
                no_improve += 1
            else:
                for cand in round_cands:
                    cand.iteration = i
                    best, no_improve = self._intake(
                        cand, spec, priors, candidates, problems, report,
                        best, no_improve)
                self._stream(run_dir, candidates, best, report)

            # ---- adversary hardens the suite (needs a live best)
            if best is not None and i < n_iter:
                added = self._adversary_pass(spec, best)
                if added:
                    report.hostile_workloads_added.append(added)
                    # re-grade best on the hardened suite
                    best.result = self._ground(best.code, spec)
                    self._stream(run_dir, candidates, best, report)

            # ---- synthesizer steers
            directive = self._synthesize(i, n_iter, candidates, best, no_improve)
            if directive == "STOP":
                report.stopped_reason = f"synthesizer stop at iteration {i}"
                break
            problems = problems[-4:]       # bounded feedback

        # ---- declared verdict vs baseline
        self._declare_verdict(report, best, baseline, spec)
        if best is not None:
            report.best_id = best.id
            report.best_quality = best.quality
            (run_dir / "best_solution.py").write_text(best.code,
                                                      encoding="utf-8")
        self._stream(run_dir, candidates, best, report, final=True)
        if self.lessons is not None:
            self.lessons.add(
                f"discovery[{self.domain.name}]: verdict={report.verdict} "
                f"best_quality={report.best_quality:.3f} after "
                f"{report.iterations} iterations",
                context="improvement loop", source=run_id, tags=["discovery"])
        return report

    # -------------------------------------------------------------- builders
    def _builder_user(self, spec: SandboxSpec, candidates: list[Candidate],
                      problems: list[str], directive: str) -> str:
        tried = sorted({c.algo_class for c in candidates})
        parts = [self.domain.describe(),
                 f"Entry function: {spec.func_name}",
                 f"Approaches already tried (do something different): "
                 f"{tried or 'none yet'}"]
        if directive == "EXPLORE":
            parts.append("DIRECTIVE: the current direction stalled - propose "
                         "a structurally different algorithm class.")
        if problems:
            parts.append("OBSERVED PROBLEMS to fix:\n" +
                         "\n".join(f"- {p}" for p in problems[-4:]))
        return "\n\n".join(parts)

    def _builder_propose(self, iteration: int, spec: SandboxSpec,
                         candidates: list[Candidate], problems: list[str],
                         directive: str) -> Candidate | None:
        user = self._builder_user(spec, candidates, problems, directive)
        try:
            out: ProposalOut = self.router.structured(
                BUILDER_SYSTEM, user, ProposalOut,
                role="builder", kind="builder_propose")
            return Candidate(code=out.code, algo_class=out.algo_class,
                             rationale=out.rationale)
        except ModelError as exc:
            log.warning("builder proposal failed: %s", exc)
            return None

    def _propose_round(self, iteration: int, spec: SandboxSpec,
                       candidates: list[Candidate], problems: list[str],
                       directive: str) -> list[Candidate]:
        """One or (cfg.builder_fanout) proposals. With fanout>1 the proposals
        are generated CONCURRENTLY via router.agather — independent draws from
        the same round context, so a round explores several algorithm classes at
        once instead of one-at-a-time. fanout<=1 preserves the exact sequential
        behavior."""
        fanout = max(1, self.cfg.builder_fanout)
        if fanout == 1:
            cand = self._builder_propose(iteration, spec, candidates, problems,
                                         directive)
            return [cand] if cand is not None else []
        user = self._builder_user(spec, candidates, problems, directive)

        def _thunk():
            return self.router.astructured(
                BUILDER_SYSTEM, user, ProposalOut, role="builder",
                kind="builder_propose")
        results = asyncio.run(self.router.agather([_thunk] * fanout))
        out: list[Candidate] = []
        for r in results:
            if isinstance(r, ProposalOut):
                out.append(Candidate(code=r.code, algo_class=r.algo_class,
                                     rationale=r.rationale))
            else:
                log.warning("wide-builder proposal failed: %s", r)
        return out

    def _intake(self, cand: Candidate, spec: SandboxSpec, priors: dict,
                candidates: list[Candidate], problems: list[str],
                report: LoopReport, best: Candidate | None,
                no_improve: int) -> tuple[Candidate | None, int]:
        """Ground one candidate, score novelty, fold it into the run state, and
        update (best, no_improve). Shared by the single and wide-fanout paths so
        their bookkeeping can never diverge."""
        cand.result = self._ground(cand.code, spec)
        cand.novelty = assess_novelty(
            cand.code, priors, threshold=self.cfg.novelty_similarity)
        priors[cand.id] = node_sequence(cand.code)
        candidates.append(cand)
        report.candidates_total += 1
        if cand.result.correct:
            report.candidates_correct += 1
            if best is None or cand.quality > best.quality + 1e-9:
                return cand, 0
            return best, no_improve + 1
        problems.extend(self._problems_from(cand.result))
        return best, no_improve + 1

    def _ground(self, code: str, spec: SandboxSpec) -> SandboxResult:
        return run_sandboxed(code, spec,
                             timeout_s=self.cfg.sandbox_timeout_s,
                             mem_cap_mb=self.cfg.sandbox_mem_cap_mb,
                             bench_repeats=self.cfg.bench_repeats)

    @staticmethod
    def _problems_from(result: SandboxResult) -> list[str]:
        """Causal, problems-only feedback (expected vs got; never thresholds)."""
        out = []
        if result.safety:
            out.append(f"safety screen: {result.safety[:3]}")
        if result.error:
            out.append(f"execution: {result.error[:200]}")
        for f in result.failures[:3]:
            out.append(f"case '{f.get('case')}': expected {f.get('expected')} "
                       f"got {f.get('got')}")
        if result.mutated_input:
            out.append("candidate mutated its input arguments")
        return out

    # -------------------------------------------------------------- adversary
    def _adversary_pass(self, spec: SandboxSpec, best: Candidate) -> dict | None:
        existing = {w["name"] for w in spec.workloads}
        dists = sorted({w.get("dist", "uniform") for w in spec.workloads} |
                       {"uniform", "duplicates", "sorted", "reversed", "skewed"})
        user = (f"{self.domain.describe()}\n\n"
                f"Generator dists available: {dists}\n"
                f"Current best measured quality by workload: "
                f"{best.result.quality_by_workload if best.result else {}}\n"
                f"Existing workload names: {sorted(existing)}")
        try:
            out: AdversaryOut = self.router.structured(
                ADVERSARY_SYSTEM, user, AdversaryOut, role="adversary",
                kind="adversary_attack")
        except ModelError as exc:
            log.warning("adversary pass failed: %s", exc)
            return None
        wl = out.hostile_workload or {}
        if not wl.get("name") or wl["name"] in existing:
            return None
        hardened = {"name": str(wl["name"]),
                    "n": min(int(wl.get("n", 500)), 20000),
                    "dist": str(wl.get("dist", "uniform")),
                    "seed": int(wl.get("seed", 1)),
                    "k": int(wl.get("k", 10))}
        spec.workloads.append(hardened)
        log.info("adversary hardened suite with workload %s", hardened["name"])
        return hardened

    # ------------------------------------------------------------ synthesizer
    def _synthesize(self, i: int, n_iter: int, candidates: list[Candidate],
                    best: Candidate | None, no_improve: int) -> str:
        # deterministic protective policy first (signals are computed, not asserted)
        if no_improve >= self.cfg.stall_window:
            recombinant = sum(1 for c in candidates[-3:]
                              if c.novelty and not c.novelty.novel)
            if recombinant >= 2:
                return "EXPLORE"
        if i >= n_iter:
            return "STOP"
        try:
            out: SynthOut = self.router.structured(
                SYNTH_SYSTEM,
                f"iteration {i}/{n_iter}; correct so far: "
                f"{sum(1 for c in candidates if c.result and c.result.correct)}; "
                f"best quality: {best.quality if best else None}; "
                f"iterations without improvement: {no_improve}; "
                f"classes tried: {sorted({c.algo_class for c in candidates})}",
                SynthOut, role="judge", kind="synthesizer_decide")
            action = out.action.upper().strip()
            return action if action in ("CONTINUE", "EXPLORE", "STOP") \
                else "CONTINUE"
        except ModelError:
            return "CONTINUE" if no_improve < self.cfg.stall_window else "EXPLORE"

    # ----------------------------------------------------------- declarations
    def _declare_verdict(self, report: LoopReport, best: Candidate | None,
                         baseline: Candidate | None, spec: SandboxSpec) -> None:
        """Declared rule (recorded verbatim in the artifact):
        margins = best.quality_by_workload - baseline.quality_by_workload,
        per workload, on the FINAL (hardened) suite; mean(margin) > eps ->
        beats; >= -eps -> matches; else below. fragile <=> any per-workload
        margin lands in a different region than the mean."""
        eps = self.cfg.utility_eps
        report.declared_rule = (
            f"mean per-workload quality margin vs baseline on final suite; "
            f"beats > {eps}, matches >= -{eps}, else below; fragile if any "
            f"workload margin region differs from mean region")
        if best is None or baseline is None or not baseline.result or \
                not baseline.result.correct or not best.result:
            report.verdict = "no_baseline" if best else "no_candidate"
            return
        # re-grade baseline on the final (possibly hardened) suite
        baseline.result = self._ground(baseline.code, spec)
        if not baseline.result.correct:
            report.verdict = "baseline_failed_hardened_suite"
            return
        report.baseline_quality = baseline.result.quality
        bw, cw = baseline.result.quality_by_workload, best.result.quality_by_workload
        common = sorted(set(bw) & set(cw))
        if not common:
            report.verdict = "matches" if abs(
                best.quality - baseline.result.quality) <= eps else (
                "beats" if best.quality > baseline.result.quality else "below")
            report.mean_margin = round(best.quality - baseline.result.quality, 6)
            return
        margins = {w: cw[w] - bw[w] for w in common}
        mean = sum(margins.values()) / len(margins)

        def region(x: float) -> str:
            return "beats" if x > eps else ("matches" if x >= -eps else "below")

        report.margins_by_workload = {w: round(m, 6) for w, m in margins.items()}
        report.mean_margin = round(mean, 6)
        report.verdict = region(mean)
        report.fragile = any(region(m) != report.verdict
                             for m in margins.values())

    # ---------------------------------------------------------------- stream
    @staticmethod
    def _stream(run_dir, candidates: list[Candidate], best: Candidate | None,
                report: LoopReport, *, final: bool = False) -> None:
        rows = []
        for c in candidates:
            rows.append({
                "id": c.id, "iteration": c.iteration, "origin": c.origin,
                "algo_class": c.algo_class,
                "correct": bool(c.result and c.result.correct),
                "quality": c.quality,
                "quality_by_workload": c.result.quality_by_workload if c.result else {},
                "novel": c.novelty.novel if c.novelty else None,
                "max_similarity": c.novelty.max_similarity if c.novelty else None,
                "error": (c.result.error if c.result else "")[:200],
            })
        (run_dir / "candidates.json").write_text(
            json.dumps(rows, indent=1), encoding="utf-8")
        (run_dir / "result.json").write_text(
            json.dumps(asdict(report), indent=1, default=str), encoding="utf-8")
        if final:
            lines = [f"Discovery run {report.run_id}",
                     f"domain: {report.domain}",
                     f"iterations: {report.iterations}",
                     f"candidates: {report.candidates_total} "
                     f"({report.candidates_correct} correct)",
                     f"best quality: {report.best_quality:.4f}",
                     f"baseline quality: {report.baseline_quality}",
                     f"VERDICT: {report.verdict} "
                     f"(mean margin {report.mean_margin}, "
                     f"fragile={report.fragile})",
                     f"declared rule: {report.declared_rule}",
                     f"hardened workloads: "
                     f"{[w['name'] for w in report.hostile_workloads_added]}"]
            (run_dir / "report.txt").write_text("\n".join(lines),
                                                encoding="utf-8")
