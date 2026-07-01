"""Graded posture-vs-valence curve — v3 Homeostat instrumentation (design §8.1).

Deterministic (NO live calls): sweeps valence 0 -> -1 through ``compute_posture``
and shows the posture is a CONTINUOUS function of valence — a graded curve, not a
step — ON vs OFF (OFF: flat, the unmodulated defaults). This is the "lights,
measured" for the Homeostat: it demonstrates the graded control structure v3
builds. It makes NO phenomenal claim — a curve is a control law, not a feeling.

  python -m director.bench.homeostat_curve
"""
from __future__ import annotations

from ..config import Config
from ..core.homeostat import compute_posture
from ..core.selfstate import SelfState


def curve(cfg, steps: int = 11) -> list[dict]:
    """Sweep valence 0 -> -1 (inclusive) in `steps` points; posture at each."""
    out = []
    for i in range(steps):
        v = -round(i / (steps - 1), 4)        # 0.0 .. -1.0
        p = compute_posture(SelfState(valence=v), cfg=cfg)
        out.append({"valence": v, "throughput": p.throughput,
                    "persistence": p.persistence,
                    "recovery_pressure": p.recovery_pressure,
                    "caution": p.caution})
    return out


def is_graded(rows: list[dict]) -> bool:
    """Graded = throughput takes more than one value across the sweep."""
    return len({r["throughput"] for r in rows}) > 1


def latch_valence(rows: list[dict]):
    """The first (highest) valence at which throughput hits 0 (the v1 halt)."""
    return next((r["valence"] for r in rows if r["throughput"] == 0), None)


def main() -> None:                                   # pragma: no cover (cli)
    on = Config()
    on.nervous_enabled = True
    off = Config()
    off.nervous_enabled = False
    on_rows, off_rows = curve(on), curve(off)
    print("=== v3 Homeostat — graded posture vs valence (ON) ===")
    print(f"{'valence':>8} {'thru':>5} {'persist':>8} {'recov':>6} {'caution':>8}")
    for r in on_rows:
        print(f"{r['valence']:>8} {r['throughput']:>5} {r['persistence']:>8} "
              f"{r['recovery_pressure']:>6} {r['caution']:>8}")
    print(f"\nON graded? {is_graded(on_rows)}   OFF graded? {is_graded(off_rows)} "
          f"(OFF flat = byte-identical)")
    print(f"latch endpoint (throughput 0) first at valence <= {latch_valence(on_rows)}")


if __name__ == "__main__":                            # pragma: no cover
    main()
