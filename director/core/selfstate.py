"""The Interoceptive Self-Model — nervous system v3, build-1.

A persistent, trusted, HIGHER-ORDER self-representation. ``SelfState`` carries the
*episode* (valence + trajectory + duration + peak + recovery tallies + a trusted
narrative) across cycles, reduced un-gameably from the v1 Body. It is the GNWT
global self-state + the HOT model-of-the-state the v3 design calls for.

HONEST LIMIT (load-bearing): this is the FUNCTIONAL correlate of an interoceptive
self-model — a faithful trusted summary of executed/verified outcomes. It makes
NO claim of phenomenal experience. ``recovery_resolved`` is measured against the
ACTUAL Body valence change, so "feeling better" cannot be faked by a model.

Pure reducer: ``update_self_state`` never calls a model and never reads a model's
self-report; it reduces (prior SelfState, new BodyState) -> new SelfState.
Spec: docs/superpowers/specs/2026-06-16-director2-nervous-system-v3-homeostat-design.md
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:                  # avoid a runtime import cycle (types <-> selfstate)
    from .types import BodyState

__all__ = ["SelfState", "update_self_state", "build_narrative"]


@dataclass
class SelfState:
    valence: float = 0.0                # mirror of the current body composite (<= 0)
    trajectory: str = "stable"          # "worsening" | "stable" | "improving"
    duration_cycles: int = 0            # consecutive non-calm cycles (episode length)
    peak_valence: float = 0.0           # worst valence reached this episode (<= 0)
    recovery_attempts: int = 0          # pain-reducing dispatches this episode
    recovery_resolved: int = 0          # cycles valence ACTUALLY improved (un-gameable)
    narrative: str = ""                 # higher-order trusted self-description
    updated_at: int = 0                 # cycle_seq


def _trajectory(prev_valence: float, valence: float, eps: float) -> str:
    if valence > prev_valence + eps:
        return "improving"
    if valence < prev_valence - eps:
        return "worsening"
    return "stable"


def _peak_word(peak_valence: float) -> str:
    if peak_valence <= -0.66:
        return "severe"
    if peak_valence <= -0.33:
        return "moderate"
    return "mild"


def build_narrative(duration: int, trajectory: str, peak_valence: float,
                    attempts: int, resolved: int, axis: str = "") -> str:
    """The higher-order self-description (HOT): a trusted, QUALITATIVE summary of
    the episode — problems and trajectory, never the raw valence number (the
    program's diagnoses-only ethos; the floats stay in trusted code)."""
    subject = axis.replace("_", " ") if axis else "accumulated load"
    if attempts:
        rec = (f"; {resolved} of {attempts} recovery attempt(s) measurably "
               f"reduced damage")
    else:
        rec = "; no recovery work dispatched yet"
    return (f"Under sustained {subject} for {duration} cycle(s); valence "
            f"{trajectory}; worst this episode {_peak_word(peak_valence)}{rec}.")


def update_self_state(prior: SelfState, body: BodyState, *, cfg,
                      recovery_attempts_delta: int = 0,
                      cycle_seq: int = 0, axis: str = "") -> SelfState:
    """Reduce (prior, body) -> new SelfState. Pure; un-gameable.

    An EPISODE is the span of consecutive non-calm cycles (valence at/below the
    ache threshold). duration / peak / recovery tallies reset on return to calm.
    ``trajectory`` and ``recovery_resolved`` are measured from the REAL valence
    change across cycles, never a model's claim."""
    valence = float(body.valence)
    eps = float(cfg.valence_eps)
    non_calm = valence <= float(cfg.ache_threshold)

    if not non_calm:
        return SelfState(
            valence=valence, trajectory="stable", duration_cycles=0,
            peak_valence=0.0, recovery_attempts=0, recovery_resolved=0,
            narrative="Calm: no episode open; trusted valence within the "
                      "non-pain band.",
            updated_at=cycle_seq)

    continuing = prior.duration_cycles > 0
    duration = prior.duration_cycles + 1 if continuing else 1
    peak = min(valence, prior.peak_valence) if continuing else valence
    traj = _trajectory(prior.valence, valence, eps) if continuing else "worsening"
    attempts = (prior.recovery_attempts if continuing else 0) \
        + max(0, recovery_attempts_delta)
    # un-gameable recovery: this cycle counts as resolved iff valence ACTUALLY
    # improved over the prior cycle during an open episode (measured, not claimed).
    improved = continuing and valence > prior.valence + eps
    resolved = (prior.recovery_resolved if continuing else 0) + (1 if improved else 0)

    return SelfState(
        valence=valence, trajectory=traj, duration_cycles=duration,
        peak_valence=peak, recovery_attempts=attempts, recovery_resolved=resolved,
        narrative=build_narrative(duration, traj, peak, attempts, resolved, axis),
        updated_at=cycle_seq)
