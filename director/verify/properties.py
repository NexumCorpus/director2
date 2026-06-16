"""Trusted necessary-condition checkers — the engine of VERIFIED_PARTIAL.

The boundary (RDE-evaluated): you cannot manufacture ground truth where there
is no oracle. But where a TRUSTED (human/hook-authored, reviewed-source)
checker can decide a *necessary condition* of correctness — and that checker
is proven to actually reject a bad sibling, and its reference is authored
independently of the work — you have genuine PARTIAL verification: strictly
stronger than a model's JUDGED guess, strictly weaker than a full oracle.

This module is that trusted layer. Every checker here is hand-written. None is
synthesized per task (that would re-open generator-grades-itself). A checker
counts toward VERIFIED_PARTIAL only if :func:`run_properties` proves it
force-to-fails on this deliverable; the caller additionally asserts the
reference's provenance is independent (the lineage guard). The product is a
report dict; :func:`partial_bundle_ok` is the single gate convictions trusts.

What this NEVER claims: that the deliverable is *correct* or *true*. A
schema-valid scenario can be operationally worthless. Validity is not truth —
trusted code decides validity; truth stays JUDGED.
"""

from __future__ import annotations

import json
import re

from .mutations import code_breaking_mutants, shape_preserving_mutants

#: checkers that operate on CODE — their force-to-fail uses code-breaking mutants
#: (syntax/runtime errors), not shape-preserving value mutants.
_CODE_CHECKS = frozenset({"python_parses", "code_runs", "tests_pass"})

_ID_KEYS = ("id", "ref", "refs", "artifact_id", "artifact_ids", "cites",
            "source", "sources")
_ID_RE = re.compile(r"^[0-9a-f]{8,}$")


def _as_obj(target):
    if isinstance(target, (dict, list)):
        return target
    if isinstance(target, str):
        try:
            return json.loads(target)
        except (json.JSONDecodeError, ValueError):
            return target
    return target


def _validate_schema(inst, schema) -> tuple[bool, str]:
    """Necessary-condition validator (subset of JSON-Schema): types, required
    keys, AND value constraints (minimum/maximum/minItems/maxItems/enum/
    pattern/minLength). The value constraints are what make this DISCRIMINATE
    wrong values, not just wrong shape — a pure-shape schema (no value
    constraints) cannot earn a partial-verify count (see run_properties).
    Still only a NECESSARY condition: validity is not truth."""
    t = schema.get("type")
    if t == "object":
        if not isinstance(inst, dict):
            return False, "expected object"
        for req in schema.get("required", []):
            if req not in inst:
                return False, f"missing required '{req}'"
        for k, sub in (schema.get("properties") or {}).items():
            if k in inst:
                ok, why = _validate_schema(inst[k], sub)
                if not ok:
                    return False, f"{k}: {why}"
    elif t == "array":
        if not isinstance(inst, list):
            return False, "expected array"
        if "minItems" in schema and len(inst) < schema["minItems"]:
            return False, f"fewer than {schema['minItems']} items"
        if "maxItems" in schema and len(inst) > schema["maxItems"]:
            return False, f"more than {schema['maxItems']} items"
        items = schema.get("items")
        if items:
            for i, el in enumerate(inst):
                ok, why = _validate_schema(el, items)
                if not ok:
                    return False, f"[{i}]: {why}"
    elif t == "integer":
        if isinstance(inst, bool) or not isinstance(inst, int):
            return False, "expected integer"
    elif t == "number":
        if isinstance(inst, bool) or not isinstance(inst, (int, float)):
            return False, "expected number"
    elif t == "string":
        if not isinstance(inst, str):
            return False, "expected string"
    elif t == "boolean":
        if not isinstance(inst, bool):
            return False, "expected boolean"
    # ---- value constraints (the value-discriminating teeth) ----
    if "enum" in schema and inst not in schema["enum"]:
        return False, "not in enum"
    if isinstance(inst, (int, float)) and not isinstance(inst, bool):
        if "minimum" in schema and inst < schema["minimum"]:
            return False, f"< minimum {schema['minimum']}"
        if "maximum" in schema and inst > schema["maximum"]:
            return False, f"> maximum {schema['maximum']}"
    if isinstance(inst, str):
        if "minLength" in schema and len(inst) < schema["minLength"]:
            return False, "too short"
        pat = schema.get("pattern")
        if pat and not re.search(pat, inst):
            return False, "pattern mismatch"
    return True, "ok"


def _collect_ids(obj) -> set:
    found = set()

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in _ID_KEYS:
                    for x in (v if isinstance(v, list) else [v]):
                        if isinstance(x, str):
                            found.add(x)
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(obj)
    return {x for x in found if _ID_RE.match(x)}


# --------------------------------------------------------------------------- #
# Trusted checker library — fn(target, ref) -> (passed, detail)
# --------------------------------------------------------------------------- #

def _c_parses(target, ref):
    o = _as_obj(target)
    return isinstance(o, (dict, list)), "parses as JSON object/array"


def _c_nonempty(target, ref):
    o = _as_obj(target)
    if isinstance(o, dict):
        return len(o) > 0, "object non-empty"
    if isinstance(o, list):
        return len(o) > 0, "array non-empty"
    return bool(str(target).strip()), "non-empty"


def _c_schema_valid(target, ref):
    if not isinstance(ref, dict):
        return False, "no reference schema supplied"
    return _validate_schema(_as_obj(target), ref)


def _c_python_parses(target, ref):
    """Necessary condition for a code deliverable: it is valid Python syntax.
    Pure (ast.parse), deterministic, no execution."""
    import ast
    src = target if isinstance(target, str) else str(target)
    try:
        ast.parse(src)
        return True, "valid Python syntax"
    except SyntaxError as exc:
        return False, f"SyntaxError: {exc.msg} (line {exc.lineno})"
    except (ValueError, TypeError) as exc:
        return False, f"not parseable: {exc}"


def _c_code_runs(target, ref):
    """Necessary condition: the code deliverable EXECUTES in isolation (imports
    resolve, no top-level crash). A real run, not a judgement — trusted because
    the harness is reviewed source and the code is screened + sandboxed."""
    from .execution import run_module
    return run_module(target if isinstance(target, str) else str(target))


def _c_tests_pass(target, ref):
    """Necessary condition: the test deliverable PASSES against its reference
    code (``ref`` = the upstream implementation source). Runs pytest in
    isolation. Independent lineage (ref authored by a different task) is the
    caller's guard, as for schema_valid."""
    from .execution import run_pytest
    if not isinstance(ref, str) or not ref.strip():
        return False, "no reference implementation supplied"
    return run_pytest(ref, target if isinstance(target, str) else str(target))


def _c_cited_ids_resolve(target, ref):
    known = set(ref or [])
    cited = _collect_ids(_as_obj(target))
    if not cited:
        return False, "no ids cited (vacuous)"   # nothing to resolve -> fail
    missing = cited - known
    return (not missing), (f"{len(cited)} ids resolve" if not missing
                           else f"unresolved: {sorted(missing)[:3]}")


def _c_totals_conserved(target, ref):
    o = _as_obj(target)
    checked = 0

    def walk(d):
        nonlocal checked
        if isinstance(d, dict):
            if "total" in d and "parts" in d \
                    and isinstance(d["parts"], list):
                try:
                    s = sum(float(x) for x in d["parts"])
                    checked += 1
                    if abs(float(d["total"]) - s) > 1e-6:
                        return False
                except (TypeError, ValueError):
                    return False
            return all(walk(v) for v in d.values())
        if isinstance(d, list):
            return all(walk(v) for v in d)
        return True
    ok = walk(o)
    if checked == 0:
        return False, "no total/parts pair to conserve (vacuous)"
    return ok, f"{checked} total(s) conserved" if ok else "total != sum(parts)"


#: name -> (fn, needs_ref). All TRUSTED, hand-written, reviewed source.
CHECKERS = {
    "parses": (_c_parses, False),
    "nonempty": (_c_nonempty, False),
    "schema_valid": (_c_schema_valid, True),
    "cited_ids_resolve": (_c_cited_ids_resolve, True),
    "totals_conserved": (_c_totals_conserved, False),
    "python_parses": (_c_python_parses, False),
    "code_runs": (_c_code_runs, False),
    "tests_pass": (_c_tests_pass, True),     # ref = upstream implementation src
}


# --------------------------------------------------------------------------- #
# Runner + the bundle gate
# --------------------------------------------------------------------------- #

def run_properties(target, names, *, ref=None,
                   ref_independent: bool = True) -> dict:
    """Run trusted checkers over a deliverable and PROVE each force-to-fails.

    A checker counts only if (a) it passes on the real target AND (b) it
    rejects at least one mutant (anti-vacuity — "a test that never fails proves
    nothing"). ``ref_independent`` is the lineage-guard verdict supplied by the
    caller: True iff any reference used was authored independently of the
    deliverable's author. Returns the report dict that backs VERIFIED_PARTIAL.
    """
    checks = []
    for name in names:
        spec = CHECKERS.get(name)
        if spec is None:
            checks.append({"name": name, "passed": False,
                           "counted": False, "detail": "unknown checker"})
            continue
        fn, needs_ref = spec
        try:
            passed, detail = fn(target, ref)
        except Exception as exc:                       # noqa: BLE001
            passed, detail = False, f"checker error: {exc}"
        # force-to-fail, DE-VACUIFIED (red-team fix): the checker must reject a
        # SHAPE-PRESERVING wrong sibling — proving it discriminates VALUES, not
        # just shape. A shape-only checker (e.g. schema_valid over a schema
        # with no value constraints) rejects none of these and so cannot count.
        n_mut = 0
        rejects_value_mutant = False
        if name == "tests_pass":
            # discrimination for a TEST = it must FAIL against a behaviorally
            # broken implementation. Mutate the REFERENCE (not the test): a
            # vacuous test (asserts nothing about the impl) still passes against a
            # no-op stub, so it cannot earn a count (red-team: tests_pass was
            # forgeable by `assert True`). Mutating the test file only proved the
            # runner read it — the wrong thing.
            from .mutations import neutralized_impl
            broken_ref = neutralized_impl(ref)
            for mref in ([broken_ref] if broken_ref else []):
                n_mut += 1
                try:
                    mp, _ = fn(target, mref)       # same test, broken impl
                except Exception:                  # noqa: BLE001
                    mp = False
                if not mp:                         # the test caught it -> discriminates
                    rejects_value_mutant = True
                    break
        else:
            _muts = (code_breaking_mutants if name in _CODE_CHECKS
                     else shape_preserving_mutants)
            for _mname, mutant in _muts(target):
                n_mut += 1
                try:
                    mp, _ = fn(mutant, ref)
                except Exception:                          # noqa: BLE001
                    mp = False
                if not mp:
                    rejects_value_mutant = True
                    break
        # if no mutant could even be generated, we cannot prove discrimination
        discriminates = rejects_value_mutant and n_mut > 0
        counted = bool(passed) and discriminates
        checks.append({"name": name, "passed": bool(passed),
                       "force_to_fail_ok": discriminates,
                       "needs_ref": needs_ref, "counted": counted,
                       "detail": detail})
    counted = [c for c in checks if c["counted"]]
    return {
        "trusted": True,                 # every checker here is reviewed source
        "checks": checks,
        "n_passed": len(counted),
        "n_total": sum(1 for c in checks
                       if c.get("force_to_fail_ok")),   # checkable denominator
        "force_to_fail_ok": all(c.get("force_to_fail_ok")
                                for c in checks if c["passed"]),
        "lineage_ok": bool(ref_independent),
    }


def partial_bundle_ok(report: dict | None) -> bool:
    """The LOGICAL gate convictions trusts: a VERIFIED_PARTIAL is honest iff its
    report is trusted, lineage-independent, at least one counted check passed,
    and every passing check was proven force-to-failable. Anything else degrades
    to JUDGED.

    Signature/tamper checking is a SEPARATE concern (verify.signing.
    report_binding_ok), enforced at the display/integrity boundaries where the
    carrying artifact and deliverable are available — a report's signature must
    be BOUND to its context, which this content-only gate cannot see."""
    if not isinstance(report, dict):
        return False
    return bool(report.get("trusted")) and bool(report.get("lineage_ok")) \
        and bool(report.get("force_to_fail_ok")) \
        and int(report.get("n_passed", 0)) >= 1
