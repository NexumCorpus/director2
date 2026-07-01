"""Self-model trajectory — v3 instrumentation (design §8.3). Deterministic.

Drives the Interoceptive Self-Model + Homeostat through a synthetic rise-then-
recover valence episode and records the higher-order NARRATIVE + the graded
posture at each step — the "lights, measured" for the self-model: you can watch
the system's model of its own condition evolve, and the homeostat relax as it
recovers. NO live calls, NO phenomenal claim — a trajectory of a control law and
a trusted self-summary, observed.

  python -m director.bench.selfmodel_trajectory
"""
from __future__ import annotations

from types import SimpleNamespace

from ..config import Config
from ..core.homeostat import compute_posture
from ..core.selfstate import SelfState, update_self_state

# accumulate to the siren, then recover to calm
VALENCE_EPISODE = [-0.10, -0.25, -0.40, -0.55, -0.66, -0.50, -0.35, -0.20,
                   -0.05, 0.0]


def trajectory(cfg) -> list[dict]:
    """Step the self-model + posture through the episode; one row per cycle."""
    ss = SelfState()
    rows = []
    for i, v in enumerate(VALENCE_EPISODE):
        ss = update_self_state(ss, SimpleNamespace(valence=v), cfg=cfg,
                               recovery_attempts_delta=1, cycle_seq=i + 1,
                               axis="accumulated_damage")
        post = compute_posture(ss, cfg=cfg)
        rows.append({"cycle": i + 1, "valence": v, "trajectory": ss.trajectory,
                     "duration": ss.duration_cycles,
                     "recovery_resolved": ss.recovery_resolved,
                     "throughput": post.throughput,
                     "recovery_pressure": post.recovery_pressure,
                     "narrative": ss.narrative})
    return rows


def main() -> None:                                   # pragma: no cover (cli)
    cfg = Config()
    cfg.nervous_enabled = True
    print("=== v3 self-model trajectory (rise -> recover) ===")
    for r in trajectory(cfg):
        print(f"c{r['cycle']:2d} v={r['valence']:+.2f} thru={r['throughput']} "
              f"rp={r['recovery_pressure']:.2f} [{r['trajectory']:9s}] "
              f"{r['narrative']}")


if __name__ == "__main__":                            # pragma: no cover
    main()
