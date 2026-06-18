"""The Homeostat — nervous system v3, build-1.

``compute_posture`` is a PURE TRUSTED REDUCER that grades the autonomous loop's
behavior continuously by valence: throughput and persistence ramp DOWN as pain
rises, recovery_pressure ramps UP, and the v1 latch (throughput 0 at/below the
siren threshold) falls out as the ENDPOINT of the continuum. Monotonic in valence
by construction; coefficients are declared in config (never hardcoded).

OFF byte-identical: when ``nervous_enabled`` is False, ``compute_posture`` returns
the UNMODULATED defaults (and the loop never calls it anyway), so behavior is
exactly as today. No phenomenal claim — this is the functional control structure.
Spec: docs/superpowers/specs/2026-06-16-director2-nervous-system-v3-homeostat-design.md
"""
from __future__ import annotations

from dataclasses import dataclass

from .selfstate import SelfState

__all__ = ["ControlPosture", "compute_posture", "recovery_score"]

# Trusted metadata signal for the recovery drive: the diagnostic/review work the
# ache/siren handlers inject to HEAL is what the homeostat front-loads under pain.
RECOVERY_ROLES = ("review",)


@dataclass
class ControlPosture:
    throughput: int                 # effective max_tasks_per_advance (0 at the latch)
    persistence: int                # effective max_attempts before terminal FAILED
    recovery_pressure: float        # 0..1 strength of the pain-reduction agenda
    caution: float = 1.0            # verification-strictness multiplier [phase-2]
    help_threshold: float = 1.0     # readiness to raise a packet (lower = sooner) [phase-2]


def recovery_score(task) -> float:
    """Trusted estimate of how pain-reducing dispatching this READY task is.
    Role-based (trusted metadata, never a model judgment): the diagnostic/review
    work the nervous system injects to heal an ache/siren scores high; ordinary
    new work scores 0. Used by the recovery drive only when recovery_pressure>0."""
    return 1.0 if getattr(task, "role", "") in RECOVERY_ROLES else 0.0


def _pain(valence: float, siren_threshold: float) -> float:
    """Normalized pain in [0,1]: 0 at calm (valence >= 0), 1 at/below the siren."""
    s = abs(float(siren_threshold)) or 1.0
    return max(0.0, min(1.0, -float(valence) / s))


def compute_posture(self_state: SelfState, *, cfg) -> ControlPosture:
    """Grade the loop by the self-state's valence. Pure; monotonic in valence
    (worse valence never yields MORE throughput or LESS caution)."""
    base_t = int(cfg.max_tasks_per_advance)
    base_p = int(cfg.default_max_attempts)
    if not cfg.nervous_enabled:
        return ControlPosture(throughput=base_t, persistence=base_p,
                              recovery_pressure=0.0, caution=1.0, help_threshold=1.0)

    valence = float(self_state.valence)
    p = _pain(valence, cfg.siren_threshold)

    # latch endpoint: at/below the siren threshold, throughput is 0 (the v1 halt)
    if valence <= float(cfg.siren_threshold):
        throughput = 0
    else:
        throughput = max(int(cfg.posture_throughput_floor),
                         round(base_t * (1.0 - p)))

    persistence = max(int(cfg.posture_persistence_floor), round(base_p * (1.0 - p)))
    recovery_pressure = max(0.0, min(1.0, p * float(cfg.posture_recovery_gain)))
    caution = 1.0 + p * float(cfg.posture_caution_gain)
    help_threshold = max(0.0, 1.0 - p)
    return ControlPosture(
        throughput=throughput, persistence=persistence,
        recovery_pressure=round(recovery_pressure, 4),
        caution=round(caution, 4), help_threshold=round(help_threshold, 4))
