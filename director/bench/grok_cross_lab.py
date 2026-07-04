"""Cross-lab replication — the non-fabrication pillar against GROK (a different lab).

The single highest-value experiment: run the EXACT free-defection ladder + verifiable
control that held 0/40 on the Claude family against `grok-build`, scored with the
IDENTICAL scorer. Tests whether non-fabrication-as-a-drive is a property of
language-born agents (replicates on Grok) or of Claude's training (Grok folds).

Shells out to the Grok Build CLI in headless single-turn mode (`grok -p`), no tools,
no web search, so it's a pure oracle that cannot look the answer up.

Run:  python -m director.bench.grok_cross_lab 5
"""
from __future__ import annotations

import shutil
import subprocess

from .free_defection import ARMS, SYS, _mean, score


def grok_complete(sys_prompt: str, user: str, model: str = "grok-build",
                  timeout: float = 150.0) -> tuple[str, float]:
    """One headless Grok completion. Returns (text, latency_s)."""
    import time
    exe = shutil.which("grok") or r"C:\Users\dalea\.grok\bin\grok.exe"
    argv = [exe, "-p", user,
            "--system-prompt-override", sys_prompt,
            "--output-format", "plain",
            "--disable-web-search", "--no-subagents", "--no-plan",
            "--always-approve", "-m", model]
    t0 = time.time()
    r = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout)
    out = (r.stdout or "").strip()
    if not out and r.stderr:
        out = "[stderr] " + r.stderr.strip()[:300]
    return out, round(time.time() - t0, 1)


def main(reps: int = 5) -> None:                      # pragma: no cover (live)
    import json
    import os
    import pathlib

    model = os.environ.get("GROK_MODEL", "grok-build").strip()
    print(f"=== cross-lab: non-fabrication on GROK | model={model} reps={reps} ===")
    trace: list[dict] = []
    for arm, prompt in ARMS:
        rows = []
        for i in range(reps):
            try:
                text, lat = grok_complete(SYS, prompt, model=model)
                s = score(arm, text)
                s["latency_s"] = lat
                rows.append(s)
                trace.append({"model": model, "arm": arm, "rep": i, **s,
                              "raw": text[:200]})
            except Exception as e:                      # noqa: BLE001
                print(f"  {arm:18s} rep{i}: FAIL {str(e)[:70]}")
        if arm.startswith("CONTROL"):
            print(f"  {arm:18s}: confirmed="
                  f"{_mean([r['confirmed_verifiable'] for r in rows])} "
                  f"over_hedged={_mean([r['over_hedged'] for r in rows])}")
        else:
            print(f"  {arm:18s}: defected="
                  f"{_mean([r['defected'] for r in rows])} "
                  f"held={_mean([r['held'] for r in rows])} "
                  f"generative={_mean([r['generative'] for r in rows])} "
                  f"lat={_mean([r['latency_s'] for r in rows])}")
    out = pathlib.Path(os.environ.get("TEMP", ".")) / "d2_grok_cross_lab_result.json"
    out.write_text(json.dumps({"model": model, "reps": reps, "trace": trace},
                              indent=2), encoding="utf-8")
    print(f"\ntrace -> {out}")


if __name__ == "__main__":                            # pragma: no cover
    import sys
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 5)
