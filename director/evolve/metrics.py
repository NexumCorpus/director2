"""PerfLedger — performance tracking for every model call.

One JSONL row per call (success or failure) under ``<home>/perf/``. The
ledger powers: cost/latency visibility (`director models --stats`), prompt
win-rates (meta-prompt evolution evidence), and backend health checks.
"""

from __future__ import annotations

import json
import threading
from collections import defaultdict
from pathlib import Path

from ..config import Config
from ..core.types import utcnow
from ..logging_setup import get_logger

log = get_logger("evolve.metrics")


class PerfLedger:
    def __init__(self, cfg: Config):
        self.path = cfg.perf_dir / "model_calls.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()      # parallel subagents append here

    # ------------------------------------------------------------- recording
    def record(self, row: dict) -> None:
        row = dict(row)
        row.setdefault("ts", utcnow().isoformat())
        line = json.dumps(row) + "\n"
        try:
            with self._lock, self.path.open("a", encoding="utf-8") as fh:
                fh.write(line)
        except OSError as exc:
            log.warning("perf record failed: %s", exc)

    @property
    def recorder(self):
        """Callable for LLMRouter(recorder=...)."""
        return self.record

    # --------------------------------------------------------------- reading
    def rows(self, *, since: str | None = None) -> list[dict]:
        if not self.path.is_file():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        if since:        # run-scoped view: only rows recorded at/after `since`
            out = [r for r in out if str(r.get("ts", "")) >= since]
        return out

    def stats(self, *, since: str | None = None) -> dict:
        """Aggregate call stats. Pass ``since`` (an ISO timestamp captured before
        a run) to scope it to a single arc — the cumulative ledger otherwise
        blends every prior run together (live finding: per-arc perf was
        unreadable)."""
        rows = self.rows(since=since)
        if not rows:
            return {"calls": 0}
        ok = [r for r in rows if r.get("ok")]
        latencies = [r["latency_s"] for r in ok
                     if isinstance(r.get("latency_s"), (int, float))]
        by_backend: dict[str, int] = defaultdict(int)
        by_kind: dict[str, dict] = defaultdict(lambda: {"calls": 0, "ok": 0})
        ptok = ctok = 0
        for r in rows:
            by_backend[r.get("backend", "?")] += 1
            k = by_kind[r.get("kind") or "?"]
            k["calls"] += 1
            k["ok"] += 1 if r.get("ok") else 0
            ptok += int(r.get("prompt_tokens") or 0)
            ctok += int(r.get("completion_tokens") or 0)
        return {
            "calls": len(rows),
            "ok_rate": round(len(ok) / len(rows), 3),
            "mean_latency_s": round(sum(latencies) / len(latencies), 3)
            if latencies else None,
            "prompt_tokens": ptok,
            "completion_tokens": ctok,
            "by_backend": dict(by_backend),
            "by_kind": {k: {"calls": v["calls"],
                            "ok_rate": round(v["ok"] / v["calls"], 3)}
                        for k, v in sorted(by_kind.items())},
        }

    def kind_ok_rate(self, kind: str, *, version: str | None = None) -> dict:
        """Win-rate for one prompt kind (optionally filtered by prompt_version
        tag) — the evidence base for meta-prompt evolution."""
        rows = [r for r in self.rows() if r.get("kind") == kind and
                (version is None or str(r.get("prompt_version")) == str(version))]
        if not rows:
            return {"kind": kind, "calls": 0, "ok_rate": None}
        ok = sum(1 for r in rows if r.get("ok"))
        return {"kind": kind, "calls": len(rows),
                "ok_rate": round(ok / len(rows), 3),
                "version": version}

    def failure_samples(self, kind: str, *, limit: int = 5) -> list[str]:
        """Recent failure messages for a kind — problems-only feedback for the
        prompt mutator (errors are problems, never rubrics)."""
        fails = [r.get("error", "") for r in self.rows()
                 if r.get("kind") == kind and not r.get("ok") and r.get("error")]
        return fails[-limit:]
