"""Isolated execution harness — the Empirical Grounding Rule, generalized.

*No claim about generated code is believed until the code has run, in
isolation, and been checked against a trusted oracle.* (RDE constitution, v0.)

The candidate is screened statically, then executed in a fresh ``python -I``
subprocess (isolated mode: no site-packages, no env inheritance, PYTHONPATH
stripped) with a hard wall-clock timeout and an optional RSS memory watchdog
(psutil, if installed). Results stream to ``result.json`` inside the scratch
dir, so a mid-run kill still leaves the correctness verdict on disk.

Contract (the RDE shape):
    solve(items, k)            -- the candidate entry point (name configurable)
    oracle(items, k)           -- trusted reference implementation
    gen_workload(n, dist, seed)-- trusted stream/workload generator
    verdict(got, expected, items, k) -> (ok: bool, quality: float)
                                -- optional; default is exact equality
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..errors import SandboxError
from ..logging_setup import get_logger
from .safety import defines_function, safety_violations, simplicity_metrics

log = get_logger("sandbox")

try:
    import psutil                                            # noqa: F401
    _HAVE_PSUTIL = True
except ImportError:
    _HAVE_PSUTIL = False


@dataclass
class SandboxSpec:
    """Everything needed to ground one problem. ``*_src`` fields are Python
    source spliced into the runner."""
    oracle_src: str
    workload_gen_src: str = ""
    criteria_cases: list = field(default_factory=list)   # [{"name", "args": [...]}]
    workloads: list = field(default_factory=list)        # [{"name","n","dist","seed","k"}]
    verdict_src: str = ""                                 # optional continuous verdict
    func_name: str = "solve"
    allowed_imports: list = field(default_factory=list)   # extra allow-list entries


@dataclass
class SandboxResult:
    correct: bool = False
    mutated_input: bool = False
    failures: list = field(default_factory=list)
    timings: dict = field(default_factory=dict)           # workload -> median secs
    quality: float = 0.0                                   # mean over workloads
    quality_by_workload: dict = field(default_factory=dict)
    peak_memory_bytes: int = 0
    error: str = ""
    timed_out: bool = False
    mem_killed: bool = False
    safety: list = field(default_factory=list)
    loc: int = 0
    ast_nodes: int = 0
    wall_s: float = 0.0
    incomplete: bool = False                               # completeness gate (RDE v10)

    @property
    def ok(self) -> bool:
        return self.correct and not self.error and not self.safety

    def summary(self) -> str:
        if self.safety:
            return f"UNSAFE: {self.safety[:3]}"
        if self.error and not self.correct:
            return f"ERROR: {self.error[:120]}"
        return (f"{'ok' if self.correct else 'INCORRECT'} | "
                f"quality={self.quality:.3f} | t={sum(self.timings.values())*1e3:.1f}ms")


_RUNNER = r'''
import copy, json, statistics, sys, time, tracemalloc

job_path = sys.argv[1]
with open(job_path, "r", encoding="utf-8") as fh:
    JOB = json.load(fh)
RESULT_PATH = JOB["result_path"]
RESULT = {"correct": False, "mutated_input": False, "failures": [],
          "timings": {}, "quality_by_workload": {}, "peak_memory_bytes": 0,
          "error": "", "stage": "start", "incomplete": False}

def _flush():
    with open(RESULT_PATH, "w", encoding="utf-8") as fh:
        json.dump(RESULT, fh)

_flush()

# Capture the stdlib callables the harness depends on BEFORE the candidate
# runs, under private names the safety screen forbids the candidate from
# rebinding (global/nonlocal are blocked; a bare top-level assignment to these
# would need to appear in candidate source, which we also screen).
_deepcopy = copy.deepcopy
_median = statistics.median
_perf = time.perf_counter

# --- candidate first -------------------------------------------------------
# The candidate's definitions land here, THEN the trusted oracle/gen/verdict
# are defined below and win any name collision. A candidate that defines its
# own `verdict`/`oracle` to forge a passing grade is overwritten by the
# trusted definitions that follow -- the grounding-integrity boundary.
__CANDIDATE_SRC__

_solve = globals().get(JOB["func_name"])

# --- trusted graders last (authoritative) ----------------------------------
__ORACLE_SRC__

__GEN_SRC__

def verdict(got, expected, items, k):
    eq = (got == expected)
    return (eq, 1.0 if eq else 0.0)

__VERDICT_SRC__

if not callable(_solve):
    RESULT["error"] = "candidate does not define a callable %r" % (
        JOB["func_name"],)
    _flush()
    sys.exit(0)

def _excerpt(v):
    s = repr(v)
    return s if len(s) <= 200 else s[:200] + "..."

try:
    RESULT["stage"] = "correctness"
    all_ok = True
    for case in JOB["criteria_cases"]:
        args = case["args"]
        snapshot = _deepcopy(args)
        expected = oracle(*_deepcopy(args))
        got = _solve(*args)
        if args != snapshot:
            RESULT["mutated_input"] = True
        ok, _q = verdict(got, expected, *snapshot)
        if not ok:
            all_ok = False
            RESULT["failures"].append({
                "case": case.get("name", "?"),
                "expected": _excerpt(expected), "got": _excerpt(got)})
    RESULT["correct"] = all_ok and not RESULT["mutated_input"]
    _flush()

    if RESULT["correct"]:
        RESULT["stage"] = "benchmark"
        repeats = int(JOB.get("bench_repeats", 3))
        for i, wl in enumerate(JOB.get("workloads", [])):
            try:
                items = gen_workload(wl["n"], wl.get("dist", "uniform"),
                                     wl.get("seed", 0))
                k = wl.get("k", 1)
                if i == 0:
                    tracemalloc.start()
                    _solve(_deepcopy(items), k)
                    _cur, peak = tracemalloc.get_traced_memory()
                    tracemalloc.stop()
                    RESULT["peak_memory_bytes"] = int(peak)
                times = []
                got = None
                for _ in range(repeats):
                    data = _deepcopy(items)
                    t0 = _perf()
                    got = _solve(data, k)
                    times.append(_perf() - t0)
                expected = oracle(_deepcopy(items), k)
                _ok, q = verdict(got, expected, items, k)
                RESULT["timings"][wl["name"]] = _median(times)
                RESULT["quality_by_workload"][wl["name"]] = float(q)
            except Exception as exc:                          # noqa: BLE001
                # Completeness gate: a missing measurement scores 0.0,
                # explicitly -- never silently renormalised.
                RESULT["quality_by_workload"][wl["name"]] = 0.0
                RESULT["incomplete"] = True
                RESULT["failures"].append({"case": "workload:" + wl["name"],
                                           "expected": "measurement",
                                           "got": _excerpt(exc)})
            _flush()
    RESULT["stage"] = "done"
except Exception as exc:                                      # noqa: BLE001
    import traceback
    RESULT["error"] = f"{type(exc).__name__}: {exc}"
    RESULT["traceback"] = traceback.format_exc()[-1500:]
_flush()
'''


def run_sandboxed(code: str, spec: SandboxSpec, *, timeout_s: float = 20.0,
                  mem_cap_mb: int = 1024, bench_repeats: int = 3) -> SandboxResult:
    """Screen, execute, and grade one candidate. Never raises on candidate
    failure — failures come back inside the result. Raises SandboxError only
    when the harness itself is broken."""
    result = SandboxResult()
    result.loc, result.ast_nodes = simplicity_metrics(code)

    extra = list(spec.allowed_imports)
    from .safety import DEFAULT_ALLOWED_IMPORTS
    allowed = set(DEFAULT_ALLOWED_IMPORTS) | set(extra)
    violations = safety_violations(code, allowed_imports=allowed)
    if violations:
        result.safety = violations
        result.error = "safety screen rejected candidate"
        return result
    if not defines_function(code, spec.func_name):
        result.error = f"candidate does not define {spec.func_name}()"
        return result

    # Only the TRUSTED sources are spliced into the runner text. The candidate
    # is passed through the job file and defined ahead of the trusted graders,
    # so it cannot inject runner-template tokens or shadow oracle/verdict.
    runner_src = (_RUNNER
                  .replace("__ORACLE_SRC__", spec.oracle_src)
                  .replace("__GEN_SRC__", spec.workload_gen_src or
                           "def gen_workload(n, dist, seed):\n    return []")
                  .replace("__VERDICT_SRC__", spec.verdict_src or "")
                  .replace("__CANDIDATE_SRC__", code))

    with tempfile.TemporaryDirectory(prefix="director-sbx-",
                                     ignore_cleanup_errors=True) as tmp:
        tmp_path = Path(tmp)
        runner_path = tmp_path / "runner.py"
        job_path = tmp_path / "job.json"
        result_path = tmp_path / "result.json"
        runner_path.write_text(runner_src, encoding="utf-8")
        job_path.write_text(json.dumps({
            "result_path": str(result_path),
            "func_name": spec.func_name,
            "criteria_cases": spec.criteria_cases,
            "workloads": spec.workloads,
            "bench_repeats": bench_repeats,
        }), encoding="utf-8")

        cmd = [sys.executable, "-I", str(runner_path), str(job_path)]
        t0 = time.perf_counter()
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, cwd=str(tmp_path))
        except OSError as exc:
            raise SandboxError(f"could not spawn sandbox: {exc}") from exc

        result.timed_out, result.mem_killed = _watch(proc, timeout_s, mem_cap_mb)
        result.wall_s = time.perf_counter() - t0
        try:
            _stdout, stderr = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            # kill() already issued by _watch; drain without a deadline so a
            # slow pipe-close on Windows cannot raise out of run_sandboxed.
            proc.kill()
            _stdout, stderr = proc.communicate()

        if result_path.is_file():
            try:
                data = json.loads(result_path.read_text(encoding="utf-8"))
                result.correct = bool(data.get("correct"))
                result.mutated_input = bool(data.get("mutated_input"))
                result.failures = data.get("failures", [])
                result.timings = data.get("timings", {})
                result.quality_by_workload = data.get("quality_by_workload", {})
                result.peak_memory_bytes = int(data.get("peak_memory_bytes", 0))
                result.incomplete = bool(data.get("incomplete"))
                if data.get("error"):
                    result.error = data["error"]
            except (json.JSONDecodeError, OSError) as exc:
                result.error = f"unreadable sandbox result: {exc}"
        if result.timed_out:
            result.error = (result.error or
                            f"wall-clock timeout after {timeout_s:.1f}s")
            result.correct = False
        if result.mem_killed:
            result.error = result.error or f"memory cap {mem_cap_mb}MB exceeded"
            result.correct = False
        if not result.error and not result_path.is_file():
            result.error = ("sandbox produced no result; stderr: " +
                            stderr.decode("utf-8", "replace")[-400:])

    qbw = result.quality_by_workload
    if result.correct:
        result.quality = (sum(qbw.values()) / len(qbw)) if qbw else 1.0
    return result


def _watch(proc: subprocess.Popen, timeout_s: float,
           mem_cap_mb: int) -> tuple[bool, bool]:
    """Poll until exit; enforce wall-clock + (if psutil) RSS cap.
    Returns (timed_out, mem_killed)."""
    deadline = time.monotonic() + timeout_s
    ps_proc = None
    if _HAVE_PSUTIL:
        try:
            ps_proc = psutil.Process(proc.pid)
        except psutil.Error:
            ps_proc = None
    while proc.poll() is None:
        if time.monotonic() > deadline:
            proc.kill()
            return True, False
        if ps_proc is not None:
            try:
                if ps_proc.memory_info().rss > mem_cap_mb * 1024 * 1024:
                    proc.kill()
                    return False, True
            except psutil.Error:
                ps_proc = None
        time.sleep(0.02)
    return False, False
