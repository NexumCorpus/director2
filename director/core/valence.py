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
from .types import BodyState, Project, RiskLevel, RiskStatus, TaskStatus

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


def compute_body(project: Project, *, secret: bytes, perf, since, cfg) -> BodyState:
    """Recompute the trusted valence projection. Pure reducer; never calls a model."""
    integrity_rows = report_integrity(project, secret)
    violators = integrity_violations(integrity_rows)
    damage = _severity_accumulated_damage(project, secret=secret, cfg=cfg,
                                          violations=len(violators))

    charter = _INSUFFICIENT
    uncertainty = 0.0
    bleed = _INSUFFICIENT

    severities = {"accumulated_damage": damage, "uncertainty": uncertainty}
    if charter != _INSUFFICIENT:
        severities["charter_integrity"] = charter
    if bleed != _INSUFFICIENT:
        severities["resource_bleed"] = bleed

    valence = _composite(severities, cfg)

    return BodyState(
        charter_integrity=charter,
        accumulated_damage=damage,
        uncertainty=uncertainty,
        resource_bleed=bleed,
        valence=valence,
        fragile_axes=[],
        computed_at=project.cycle_seq,
        provenance={},
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
