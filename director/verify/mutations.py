"""Trusted, hand-written deliverable mutators — the force-to-fail harness.

A necessary-condition checker only earns a place above JUDGED if trusted code
can show it actually REJECTS a known-bad sibling of the deliverable. "A test
that never fails proves nothing." This module supplies the known-bad siblings:
generic, content-agnostic corruptions of a deliverable (a dict / JSON / text),
written ONCE by a human and reviewed — never synthesized per task, which would
re-open the generator-grades-itself recursion.

Two DISJOINT families so the mutant set is not itself in-distribution with any
single checker's blind spot:
  * STRUCTURAL — drop a field, blank a section, truncate, duplicate.
  * VALUE      — negate a number, flip a bool, swap a string, zero-out.

:func:`mutants` yields (name, mutated_copy) pairs; the property runner applies
a checker to each and requires at least one rejection.
"""

from __future__ import annotations

import copy
import json
from typing import Iterator


def _walk_dicts(obj):
    """Yield every dict reachable in a nested structure (for targeted edits)."""
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk_dicts(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_dicts(v)


def _as_struct(target):
    """Normalize a deliverable into a mutable structure. Strings that parse as
    JSON are mutated structurally; otherwise text mutation is used."""
    if isinstance(target, (dict, list)):
        return copy.deepcopy(target), "struct"
    if isinstance(target, str):
        try:
            return json.loads(target), "json-str"
        except (json.JSONDecodeError, ValueError):
            return target, "text"
    return target, "scalar"


def _reser(obj, mode):
    return json.dumps(obj) if mode == "json-str" else obj


def mutants(target) -> Iterator[tuple[str, object]]:
    """Yield (mutation_name, corrupted_target) over two disjoint families.
    Content-agnostic: works on dicts, JSON strings, plain text."""
    struct, mode = _as_struct(target)

    # ---- STRUCTURAL family ----
    if isinstance(struct, dict) and struct:
        # drop a required-looking field
        k = next(iter(struct))
        d = copy.deepcopy(struct); d.pop(k, None)
        yield (f"drop_field:{k}", _reser(d, mode))
        # blank every string value
        d = copy.deepcopy(struct)
        for sub in _walk_dicts(d):
            for kk, vv in list(sub.items()):
                if isinstance(vv, str):
                    sub[kk] = ""
        yield ("blank_strings", _reser(d, mode))
    if isinstance(struct, list) and struct:
        yield ("drop_first", _reser(struct[1:], mode))
        yield ("duplicate_first", _reser([struct[0]] + struct, mode))
    if isinstance(struct, str):
        yield ("truncate_half", struct[: max(1, len(struct) // 2)])
        yield ("blank_text", "")

    # ---- VALUE family ----
    if isinstance(struct, (dict, list)):
        d = copy.deepcopy(struct)
        changed = False
        for sub in _walk_dicts(d):
            for kk, vv in list(sub.items()):
                if isinstance(vv, bool):
                    sub[kk] = not vv; changed = True
                elif isinstance(vv, (int, float)):
                    sub[kk] = -(vv) - 7; changed = True   # negate + perturb
        if changed:
            yield ("negate_numbers_flip_bools", _reser(d, mode))
    # always offer a wholesale wrong value so EVERY checker has a hostile case
    yield ("replace_with_empty", _reser({} if isinstance(struct, dict)
                                        else ([] if isinstance(struct, list)
                                              else ""), mode))


def neutralized_impl(code) -> str | None:
    """A behavior-NEUTRALIZED sibling of an implementation: same top-level
    functions/classes/signatures, but every body replaced with ``return None``.
    It still imports cleanly, so a test that asserts real behavior FAILS against
    it while a vacuous test (asserts nothing about the impl) still passes. Used as
    the force-to-fail reference for tests_pass: a test earns a count only if it
    catches this broken impl — proving it discriminates behavior, not just that
    the harness ran it (red-team: tests_pass was forgeable by `assert True`)."""
    import ast
    if not isinstance(code, str):
        return None
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None

    class _Neuter(ast.NodeTransformer):
        def visit_FunctionDef(self, node):
            self.generic_visit(node)
            node.body = [ast.Return(value=ast.Constant(value=None))]
            node.decorator_list = []
            return node
        visit_AsyncFunctionDef = visit_FunctionDef

    _Neuter().visit(tree)
    ast.fix_missing_locations(tree)
    try:
        return ast.unparse(tree)
    except (ValueError, AttributeError):
        return None


def code_breaking_mutants(code) -> Iterator[tuple[str, object]]:
    """Known-bad siblings for CODE checkers (python_parses / code_runs /
    tests_pass): a guaranteed SyntaxError and a guaranteed runtime error. A code
    checker earns a count only by rejecting one of these — proving it actually
    executes/parses the deliverable rather than rubber-stamping it. (The
    shape-preserving family is wrong for code: 'Z'*n is a valid identifier and
    parses fine, so a code checker would never reject it and could never count.)"""
    src = code if isinstance(code, str) else json.dumps(code)
    # guaranteed SyntaxError — caught by python_parses (and exec)
    yield ("syntax_error", src + "\n)(:def  <<< injected syntax error\n")
    # valid syntax but raises immediately — caught by code_runs / tests_pass
    yield ("runtime_error",
           "raise RuntimeError('forced mutant failure')\n" + src)
    # truncated mid-source — usually breaks a block
    yield ("truncate", src[: max(1, len(src) // 2)] + "\n    return\n")


def shape_preserving_mutants(target) -> Iterator[tuple[str, object]]:
    """Wrong siblings that keep the SHAPE (same keys, types, lengths) but
    corrupt the VALUES — the in-distribution adversary a structural checker is
    blind to (red-team finding: a schema-shaped garbage deliverable passed a
    shape-only checker while only mechanical mutants were rejected). A checker
    earns a count ONLY by rejecting one of these — that proves it discriminates
    values, not just shape."""
    struct, mode = _as_struct(target)
    if not isinstance(struct, (dict, list)):
        # plain text: a different non-empty string of the same length-ish
        if isinstance(struct, str) and struct.strip():
            yield ("value_swap_text", "Z" * max(1, len(struct)))
        return

    def perturb(obj, num, sstr, flipbool):
        if isinstance(obj, dict):
            return {k: perturb(v, num, sstr, flipbool) for k, v in obj.items()}
        if isinstance(obj, list):
            return [perturb(v, num, sstr, flipbool) for v in obj]
        if isinstance(obj, bool):
            return (not obj) if flipbool else obj
        if isinstance(obj, (int, float)):
            return num if num is not None else obj
        if isinstance(obj, str):
            return sstr if sstr is not None else obj
        return obj

    # each keeps the structure intact; only a value-class is corrupted
    yield ("values_far_negative", _reser(perturb(struct, -987654, None, False),
                                         mode))
    yield ("values_far_positive", _reser(perturb(struct, 987654, None, False),
                                         mode))
    yield ("strings_wrong", _reser(
        perturb(struct, None, "ZZZ_WRONG_VALUE", False), mode))
    yield ("bools_flipped", _reser(perturb(struct, None, None, True), mode))
