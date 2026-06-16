"""Empirical grounding for command-loop CODE deliverables — run them for real.

The discovery loop grounds candidate FUNCTIONS against an oracle; this grounds
ordinary code/test artifacts produced by the command loop: does the module
import + execute, and do its tests pass? Same containment as the discovery
sandbox — a static AST safety screen + an isolated ``python -I`` subprocess
(no env, no user site) with a hard wall-clock timeout — so a 'code' task moves
from a model's JUDGED guess to a TRUSTED necessary-condition check that the code
ACTUALLY runs. Still only a necessary condition: running is not correctness.

The screen here is intentionally broader than the discovery allow-list (real code
legitimately uses ``__future__``, ``__all__``, ``dataclasses``, ``typing`` …)
but keeps blocking the dangerous surface: os/subprocess/socket/file-IO/eval/exec
and the escape-dunders (``__class__``/``__globals__``/``__subclasses__``/…).
"""

from __future__ import annotations

import ast
import subprocess
import sys
import tempfile
from pathlib import Path

from .safety import (DEFAULT_ALLOWED_IMPORTS, ast_violations, regex_violations)

#: extra imports real code needs that the discovery allow-list omits. All are
#: pure-computation / concurrency / encoding stdlib with NO filesystem, network,
#: subprocess or escape primitives (those stay blocked by regex + the import
#: allow-list model). threading/queue added after a live arc false-failed a
#: token-bucket impl that legitimately used threading.Lock.
_EXEC_ALLOWED = set(DEFAULT_ALLOWED_IMPORTS) | {
    "__future__", "abc", "contextlib", "warnings", "textwrap", "unittest",
    "types", "weakref", "threading", "queue", "datetime", "uuid", "hashlib",
    "hmac", "base64", "struct", "secrets", "heapq", "bisect", "dataclasses"}

#: benign dunders (method names, module metadata) — allowed; escape-dunders
#: (__class__/__globals__/__subclasses__/__bases__/__mro__/__builtins__/
#: __getattribute__/__dict__/__code__/__closure__/__reduce__) stay BLOCKED.
_SAFE_DUNDERS = frozenset({
    "__init__", "__all__", "__name__", "__main__", "__doc__", "__repr__",
    "__str__", "__eq__", "__ne__", "__hash__", "__lt__", "__le__", "__gt__",
    "__ge__", "__enter__", "__exit__", "__iter__", "__next__", "__len__",
    "__call__", "__contains__", "__getitem__", "__setitem__", "__delitem__",
    "__post_init__", "__future__", "__annotations__", "__slots__", "__bool__",
    "__add__", "__sub__", "__mul__", "__index__", "__float__", "__int__"})


def exec_safety_violations(code: str, *, extra_allowed=()) -> list[str]:
    """Safety screen for command-loop code: broader imports + benign dunders
    allowed, but the dangerous surface (IO/net/eval/escape-dunders) still blocked.
    ``extra_allowed`` whitelists local module names (e.g. the impl-under-test that
    a test file imports)."""
    allowed = _EXEC_ALLOWED | set(extra_allowed)
    raw = regex_violations(code) + ast_violations(code, allowed_imports=allowed)
    out = []
    for v in raw:
        if v.startswith(("dunder:", "dunder-name:")):
            if v.split(":", 1)[1] in _SAFE_DUNDERS:
                continue          # benign dunder — allow
        if v == "import-from:__future__":
            continue
        out.append(v)
    return out


def _is_substantive(code: str) -> bool:
    """True if the module is more than imports/docstring/pass — so a trivial file
    can't earn an execution-grounding badge just by 'running cleanly'."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False
    for n in tree.body:
        if isinstance(n, (ast.Import, ast.ImportFrom, ast.Pass)):
            continue
        if isinstance(n, ast.Expr) and isinstance(
                getattr(n, "value", None), ast.Constant):
            continue                      # bare docstring / constant
        return True
    return False


def run_module(code: str, *, timeout_s: float = 15.0) -> tuple[bool, str]:
    """Execute a code module in isolation. Returns (ok, detail). ok iff the
    module is substantive AND runs to exit 0 (imports resolve, no top-level
    exception). Safe: AST screen + ``python -I`` subprocess + wall-clock timeout."""
    if not isinstance(code, str) or not code.strip():
        return False, "empty code"
    viol = exec_safety_violations(code)
    if viol:
        return False, "safety screen rejected: " + ", ".join(viol[:4])
    try:
        ast.parse(code)
    except SyntaxError as exc:
        return False, f"SyntaxError: {exc.msg} (line {exc.lineno})"
    if not _is_substantive(code):
        return False, "no substantive code (only imports/docstring)"
    return _run_files({"mod.py": code}, "mod.py", timeout_s)


def run_pytest(code: str, test_code: str, *,
               timeout_s: float = 30.0) -> tuple[bool, str]:
    """Run a test module against a code module in isolation (python -I -m pytest).
    Returns (ok, detail). ok iff pytest exits 0 (all collected tests pass). Both
    sources pass the safety screen first. Gracefully reports if pytest is absent."""
    for label, src in (("code", code), ("tests", test_code)):
        if not isinstance(src, str) or not src.strip():
            return False, f"empty {label}"
        # the test file legitimately imports the local impl module ('impl')
        viol = exec_safety_violations(src, extra_allowed=("impl",)
                                      if label == "tests" else ())
        if viol:
            return False, f"{label} safety screen: " + ", ".join(viol[:4])
        try:
            ast.parse(src)
        except SyntaxError as exc:
            return False, f"{label} SyntaxError: {exc.msg} (line {exc.lineno})"
    return _run_files({"impl.py": code, "test_deliverable.py": test_code},
                      None, timeout_s, pytest_target="test_deliverable.py")


def _run_files(files: dict, run_target, timeout_s: float,
               pytest_target: str | None = None) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory(prefix="director-exec-",
                                     ignore_cleanup_errors=True) as tmp:
        tmp_path = Path(tmp)
        for name, src in files.items():
            (tmp_path / name).write_text(src, encoding="utf-8")
        if pytest_target is not None:
            # -E (not -I) so the user-site pytest is importable; still ignores
            # PYTHON* env, runs in the temp cwd, screened code, hard timeout
            cmd = [sys.executable, "-E", "-m", "pytest", "-q", "-p",
                   "no:cacheprovider", pytest_target]
        else:
            cmd = [sys.executable, "-I", str(tmp_path / run_target)]
        try:
            proc = subprocess.run(cmd, cwd=str(tmp_path), capture_output=True,
                                  timeout=timeout_s)
        except subprocess.TimeoutExpired:
            return False, f"timed out after {timeout_s:.0f}s"
        except OSError as exc:
            return False, f"could not spawn: {exc}"
    out = ((proc.stdout or b"") + b"\n" + (proc.stderr or b"")).decode(
        "utf-8", "replace").strip()
    if pytest_target is not None and proc.returncode == 5:
        return False, "no tests collected"
    if (proc.stderr or b"").decode("utf-8", "replace").find(
            "No module named pytest") != -1:
        return False, "pytest not available"
    if proc.returncode == 0:
        return True, ("all tests pass" if pytest_target else
                      "module executed cleanly")
    last = out.splitlines()[-1] if out else f"exit {proc.returncode}"
    return False, last[:200]
