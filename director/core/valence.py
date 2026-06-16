"""The Body — the trusted valence pass (nervous system v1).

``compute_body`` is a PURE TRUSTED REDUCER over executed/verified state: it reads
existing signals (FAILED counts, attempts-over-max, open grounding risks,
integrity violations, fragile verification verdicts, NEEDS_VERIFY counts,
packet-coherence, run-scoped perf) and the small new Project counters, and
returns a recomputed ``BodyState`` projection.
It NEVER calls a model — that un-gameability is the load-bearing property
(Constitution principle 2). Thresholds, weights and saturation points are declared
constants in director/config.py, never hardcoded here.

Severity convention: every axis maps to s in [0, 1], where s = min(1, raw /
saturation). The composite valence = -sum(w_i * s_i) in [-1, 0]; when an axis
abstains ("insufficient") it is dropped and the remaining weights are renormalized
to sum to 1 (thresholds stay ABSOLUTE, never rescaled).
"""

from __future__ import annotations

from .integrity import (integrity_summary, integrity_violations,
                        report_integrity)
from .taskgraph import open_risks
from .convictions import evaluate_packet_coherence, honest_check
from .types import (BodyState, CheckKind, PacketStatus, Project, RiskLevel,
                    RiskStatus, TaskStatus)

__all__ = ["BodyState", "compute_body"]

_INSUFFICIENT = "insufficient"


def _clamp01(raw: float, saturation: float) -> float:
    """Severity = min(1, raw / saturation), floored at 0."""
    if saturation <= 0:
        return 0.0
    return max(0.0, min(1.0, raw / saturation))


def _severity_accumulated_damage(project: Project, *, secret: bytes,
                                 cfg, violations: int | None = None) -> float:
    """Raw damage = FAILED count + per-task attempts-over-max + open HIGH grounding
    risks + integrity-report violations + fragile verification verdicts. ``violations``
    may be passed by compute_body (computed once) so the integrity check isn't run twice."""
    failed = sum(1 for t in project.tasks.values()
                 if t.status is TaskStatus.FAILED)
    over_max = sum(max(0, t.attempts - t.max_attempts)
                   for t in project.tasks.values())
    high_risks = sum(1 for r in open_risks(project)
                     if r.level is RiskLevel.HIGH)
    if violations is None:
        violations = integrity_summary(project, secret)["violations"]
    fragile = sum(1 for run in project.runs.values()
                  for rep in run.reports if rep.fragile)
    raw = failed + over_max + high_risks + violations + fragile
    return _clamp01(raw, cfg.axis_saturation["accumulated_damage"])


def _severity_charter_integrity(project: Project, *, cfg) -> float:
    """Raw charter erosion = milestone reverts + coherence blocks + open CRITICAL
    grounding risks. Scaled by the declared charter_integrity saturation."""
    critical = sum(1 for r in open_risks(project)
                   if r.level is RiskLevel.CRITICAL)
    raw = project.milestone_reverts + project.coherence_blocks + critical
    return _clamp01(raw, cfg.axis_saturation["charter_integrity"])


def _severity_uncertainty(project: Project, *, cfg) -> float:
    """Raw uncertainty = NEEDS_VERIFY task count + JUDGED-not-VERIFIED option
    count over open (PRESENTED) packets + a no-real-choice packet-coherence signal.
    Reads honest_check and evaluate_packet_coherence; both trusted, model-free."""
    needs_verify = sum(1 for t in project.tasks.values()
                       if t.status is TaskStatus.NEEDS_VERIFY)
    judged = 0
    for pkt in project.packets.values():
        if pkt.status is not PacketStatus.PRESENTED:
            continue
        for o in pkt.options:
            kind, _ = honest_check(o, project.artifacts)
            if kind == CheckKind.JUDGED:
                judged += 1
        coh = evaluate_packet_coherence(pkt, project)
        if coh["spread"] < 2 and len(pkt.options) >= 2:
            judged += 1
    raw = needs_verify + judged
    return _clamp01(raw, cfg.axis_saturation["uncertainty"])


def _severity_resource_bleed(project: Project, *, perf, since, cfg):
    """Run-scoped token burn vs the declared token budget. Returns the
    "insufficient" sentinel (NOT 0.0) when no budget is declared or no perf
    ledger is available — the axis is DARK, not fine (Constitution g). Tokens are
    run-scoped via perf.stats(since=since)."""
    budget = cfg.budget
    if not budget or perf is None:
        return _INSUFFICIENT
    max_tokens = budget.get("max_tokens")
    if not max_tokens:
        return _INSUFFICIENT
    stats = perf.stats(since=since)
    used = int(stats.get("prompt_tokens", 0)) + \
        int(stats.get("completion_tokens", 0))
    return _clamp01(used, max_tokens)


def compute_body(project: Project, *, secret: bytes, perf, since, cfg) -> BodyState:
    """Recompute the trusted valence projection. Pure reducer; never calls a model."""
    integrity_rows = report_integrity(project, secret)
    violators = integrity_violations(integrity_rows)
    damage = _severity_accumulated_damage(project, secret=secret, cfg=cfg,
                                          violations=len(violators))

    charter = _severity_charter_integrity(project, cfg=cfg)

    uncertainty = _severity_uncertainty(project, cfg=cfg)
    bleed = _severity_resource_bleed(project, perf=perf, since=since, cfg=cfg)

    severities = {"accumulated_damage": damage, "uncertainty": uncertainty,
                  "charter_integrity": charter}
    if bleed != _INSUFFICIENT:
        severities["resource_bleed"] = bleed

    valence = _composite(severities, cfg)
    fragile = _fragile_axes(valence, severities, cfg)

    # surface the integrity violations into provenance so Phase 3's tamper hard
    # override (prov.get("integrity_violations", 0) > 0) is reachable in the
    # real wired path, not only in unit tests. Reuse the rows computed above.
    provenance = {
        "risk_ids": [r.id for r in open_risks(project)],
        "run_ids": list(project.runs),
        "integrity_violations": len(violators),
        "violation_ids": [r.get("artifact_id") for r in violators],
    }

    return BodyState(
        charter_integrity=charter,
        accumulated_damage=damage,
        uncertainty=uncertainty,
        resource_bleed=bleed,
        valence=valence,
        fragile_axes=fragile,
        computed_at=project.cycle_seq,
        provenance=provenance,
    )


def _composite(severities: dict, cfg) -> float:
    """valence = -sum(w_i * s_i) over PRESENT axes, remaining weights renormalized
    to sum to 1 so the result stays in [-1, 0] and ABSOLUTE thresholds stay comparable."""
    weights = cfg.valence_weights
    present = {ax: weights[ax] for ax in severities if ax in weights}
    total_w = sum(present.values())
    if total_w <= 0:
        return 0.0
    acc = sum((w / total_w) * severities[ax] for ax, w in present.items())
    return -round(acc, 6)


def _fragile_axes(valence: float, severities: dict, cfg) -> list[str]:
    """Knife-edge labeling (RDE v11 lesson: never silently round a verdict up).
    Fragile when within cfg.valence_eps of a decision edge: the composite within
    valence_eps of ache/siren threshold; any present axis within valence_eps of
    its 1.0 ceiling while the composite is negative. Descriptive only."""
    eps = cfg.valence_eps
    fragile: list[str] = []
    if (abs(valence - cfg.ache_threshold) <= eps
            or abs(valence - cfg.siren_threshold) <= eps):
        fragile.append("composite")
    for ax, s in severities.items():
        if isinstance(s, str):
            continue
        if abs(s - 1.0) <= eps and valence < 0.0:
            fragile.append(ax)
    return fragile


# ----------------------------------------------------------------- scream
# Declared cause strings (Constitution d: declared semantics). Tamper and
# charter_breach are HARD per-axis overrides that force a siren regardless of
# the composite — a catastrophic axis must never hide behind three healthy
# ones. grounding_damage is the composite-driven deep negative.
_SIREN_CAUSES = ("tamper", "charter_breach", "grounding_damage")

_CLEAR_RULES = {
    "tamper": "integrity re-check returns 0 violations",
    "charter_breach": "charter_integrity recovers below "
                      "charter_breach_threshold - hysteresis_margin",
    "grounding_damage": "the offending risk(s) close AND a run_properties "
                        "re-pass on the deliverable passes",
}

# axes that feed the composite, in declared order; used to attribute an ache
# to its largest-contributing axis (problems-not-rubrics).
_COMPOSITE_AXES = ("charter_integrity", "accumulated_damage",
                   "uncertainty", "resource_bleed")


def _axis_severity(body: "BodyState", axis: str) -> float:
    """Severity of one axis as a float in [0,1]; an abstaining ('insufficient')
    axis contributes 0 to attribution."""
    val = getattr(body, axis, 0.0)
    return float(val) if isinstance(val, (int, float)) else 0.0


def _largest_axis(body: "BodyState", cfg) -> str:
    """The axis carrying the most severity * weight — the one to name in the
    diagnosis. Ties resolve in declared order."""
    weights = cfg.valence_weights
    best, best_score = _COMPOSITE_AXES[0], -1.0
    for axis in _COMPOSITE_AXES:
        score = _axis_severity(body, axis) * float(weights.get(axis, 0.0))
        if score > best_score:
            best, best_score = axis, score
    return best


def evaluate_scream(project: "Project", body: "BodyState", *, cfg) -> dict | None:
    """Trusted threshold evaluator. Returns None when calm; else a dict
    {level, cause, axis, clear_rule, report}. NEVER calls a model and NEVER
    leaks the numeric valence/threshold/weights into the report (Constitution
    b: problems, not rubrics)."""
    if not cfg.nervous_enabled:
        return None

    # --- hard per-axis overrides -> siren, regardless of composite -----------
    prov = body.provenance or {}
    if int(prov.get("integrity_violations", 0)) > 0:
        return {"level": "siren", "cause": "tamper",
                "axis": "charter_integrity",
                "clear_rule": _CLEAR_RULES["tamper"],
                "report": ("Trusted integrity re-check found tampered "
                           "property report(s): signature binding INVALID. "
                           "Work is halted until the forgery is removed and "
                           "integrity re-verifies clean.")}

    ci = _axis_severity(body, "charter_integrity")
    if ci >= float(cfg.charter_breach_threshold):
        return {"level": "siren", "cause": "charter_breach",
                "axis": "charter_integrity",
                "clear_rule": _CLEAR_RULES["charter_breach"],
                "report": ("Charter integrity has breached: a CRITICAL "
                           "grounding risk is open and/or milestones reverted "
                           "/ coherence blocked the core mission. Recovery "
                           "must restore charter alignment before work "
                           "resumes.")}

    # --- composite gradient -------------------------------------------------
    v = float(body.valence)
    if v > float(cfg.ache_threshold):
        return None

    axis = _largest_axis(body, cfg)
    if v <= float(cfg.siren_threshold):
        return {"level": "siren", "cause": "grounding_damage", "axis": axis,
                "clear_rule": _CLEAR_RULES["grounding_damage"],
                "report": _diagnosis_report(project, body, axis)}

    # ache: the offending axis is the cause (an ache is a wince, not a halt)
    return {"level": "ache", "cause": axis, "axis": axis,
            "clear_rule": "", "report": _diagnosis_report(project, body, axis)}


def _diagnosis_report(project: "Project", body: "BodyState", axis: str) -> str:
    """A failing-cases + cause sentence for the offending axis — the problem,
    never the numeric valence/threshold (Constitution b)."""
    prov = body.provenance or {}
    refs = prov.get(f"{axis}_refs") or prov.get("risk_ids") or []
    detail = ("; refs: " + ", ".join(str(r) for r in refs[:5])) if refs else ""
    pretty = axis.replace("_", " ")
    return (f"Damage on {pretty}: trusted state shows accumulated failures on "
            f"this axis from executed/verified work{detail}.")
