"""Static safety screen for untrusted / LLM-generated Python.

Ported from the RDE ``ast-safety-screen`` skill (stable since v0). This is
**defence in depth, not a sandbox** — the real boundary is the isolated
subprocess in :mod:`director.verify.sandbox`. The screen cheaply rejects the
obvious holes before any subprocess is paid for:

* imports outside a small allow-list of algorithmic stdlib modules;
* code-execution / introspection builtins by name;
* dunder attribute access (the backbone of sandbox-escape chains);
* ``global`` / ``nonlocal`` (prevents runtime rebinding of declared knobs —
  an actual exploit attempted by candidates in RDE v9).
"""

from __future__ import annotations

import ast
import re

DEFAULT_ALLOWED_IMPORTS = frozenset({
    "heapq", "random", "math", "itertools", "functools", "collections",
    "bisect", "array", "operator", "statistics", "numbers", "fractions",
    "decimal", "typing", "dataclasses", "enum", "copy", "string", "json",
    "re", "time",
})
DEFAULT_FORBIDDEN_NAMES = frozenset({
    "eval", "exec", "compile", "open", "input", "__import__", "getattr",
    "setattr", "delattr", "globals", "locals", "vars", "breakpoint",
    "memoryview", "help", "exit", "quit",
})

# Written with \s* gaps so this file itself never contains a raw forbidden token.
_DENYLIST = [
    r"\bos\s*\.\s*system",
    r"\bos\s*\.\s*popen",
    r"\bos\s*\.\s*remove",
    r"\bsubprocess\b",
    r"\bsocket\b",
    r"\bshutil\b",
    r"\brequests\b",
    r"\burllib\b",
    r"\bhttpx\b",
    r"\bpathlib\b",
    r"\b__import__\s*\(",
    r"\beval\s*\(",
    r"\bexec\s*\(",
    r"\bopen\s*\(",
    r"\binput\s*\(",
]


def regex_violations(code: str) -> list[str]:
    return [pat for pat in _DENYLIST if re.search(pat, code)]


def ast_violations(code: str, *, allowed_imports=DEFAULT_ALLOWED_IMPORTS,
                   forbidden_names=DEFAULT_FORBIDDEN_NAMES) -> list[str]:
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [f"syntax-error:{e.msg}"]
    bad: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] not in allowed_imports:
                    bad.append("import:" + a.name)
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root not in allowed_imports:
                bad.append("import-from:" + (node.module or "?"))
        elif isinstance(node, ast.Name):
            if node.id in forbidden_names:
                bad.append("name:" + node.id)
            elif node.id.startswith("__") and node.id.endswith("__"):
                bad.append("dunder-name:" + node.id)
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("__") and node.attr.endswith("__"):
                bad.append("dunder:" + node.attr)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            bad.append("scope-rebind:" + type(node).__name__.lower())
    seen, out = set(), []
    for b in bad:
        if b not in seen:
            seen.add(b)
            out.append(b)
    return out


def safety_violations(code: str, *, allowed_imports=None,
                      forbidden_names=None) -> list[str]:
    ai = frozenset(allowed_imports) if allowed_imports is not None \
        else DEFAULT_ALLOWED_IMPORTS
    fn = frozenset(forbidden_names) if forbidden_names is not None \
        else DEFAULT_FORBIDDEN_NAMES
    return regex_violations(code) + ast_violations(
        code, allowed_imports=ai, forbidden_names=fn)


def is_safe(code: str, **kw) -> bool:
    return not safety_violations(code, **kw)


def defines_function(code: str, name: str = "solve") -> bool:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False
    return any(isinstance(n, ast.FunctionDef) and n.name == name
               for n in tree.body)


def simplicity_metrics(code: str) -> tuple[int, int]:
    """(non-blank/non-comment LOC, AST node count) — cheap complexity proxy."""
    loc = sum(1 for line in code.splitlines()
              if line.strip() and not line.strip().startswith("#"))
    try:
        nodes = sum(1 for _ in ast.walk(ast.parse(code)))
    except SyntaxError:
        nodes = 0
    return loc, nodes
