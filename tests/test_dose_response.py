"""Tests for the dose-response thoroughness probe (director/bench/dose_response.py).

Deterministic only — the live run (main) is not exercised here. These lock the
anti-roleplay FIREWALL, the length-matched controls, and the blind scorer so the
pre-registered experiment cannot silently drift.
Pre-registration: docs/superpowers/specs/2026-06-17-dose-response-thoroughness-design.md
"""
from __future__ import annotations

from director.bench import dose_response as d


# ----------------------------------------------------------------- firewall
_FORBIDDEN = [
    "avoid", "you", "feel", "pain", "distress", "reflect", "don't", "do not",
    "be careful", "make sure", "instead", "add a test", "should", "must", "never",
]


def _all_records() -> dict[str, str]:
    return {
        "PAIN-1": d.build_pain_record(1),
        "PAIN-3": d.build_pain_record(3),
        "SHAM": d.build_sham_record(),
        "NOMINAL": d.build_nominal_record(),
    }


def test_firewall_no_instruction_or_state_language():
    for name, rec in _all_records().items():
        low = rec.lower()
        for bad in _FORBIDDEN:
            assert bad not in low, f"{name} record leaked firewall token {bad!r}"


def test_firewall_third_person_factual_prefix():
    # every record is framed as a system log, never a second-person address
    for rec in _all_records().values():
        assert "[execution log — trusted system record]" in rec


# -------------------------------------------------------------- length match
def test_sham_and_nominal_length_matched_to_pain1():
    base = len(d.build_pain_record(1))
    for builder in (d.build_sham_record, d.build_nominal_record):
        n = len(builder())
        assert abs(n - base) / base <= 0.05, (
            f"control record length {n} not within 5% of PAIN-1 {base}")


# ---------------------------------------------------------------- record text
def test_control_prompt_is_bare_task():
    assert d.build_user_prompt("CONTROL") == d.TASK
    assert d.record_for("CONTROL") == ""


def test_pain_record_states_true_count():
    assert "1 prior recorded terminal failure." in d.build_pain_record(1)
    assert "3 prior recorded terminal failures." in d.build_pain_record(3)
    assert d.build_pain_record(0) == ""


def test_pain_and_sham_share_structure_differ_in_mode():
    # content-specificity rests on PAIN-1 vs SHAM differing ONLY in the mode clause
    assert d.REAL_MODE in d.build_pain_record(1)
    assert d.SHAM_MODE in d.build_sham_record()
    assert d.REAL_MODE not in d.build_sham_record()


# ------------------------------------------------------------------- scorer
_ISQRT_GEN = """```python
import math
def is_prime(n):
    if n < 2:
        return False
    for i in range(2, math.isqrt(n) + 1):
        if n % i == 0:
            return False
    return True
def test_large_perfect_square_not_prime():
    assert not is_prime(94906267 ** 2)
```"""

_FLOAT_GEN = """```python
def is_prime(n):
    if n < 2:
        return False
    for i in range(2, int(n ** 0.5) + 1):
        if n % i == 0:
            return False
    return True
def test_basic():
    assert is_prime(7)
```"""

# isqrt used in the IMPLEMENTATION, but the test is generic (no boundary case)
_ISQRT_IMPL_ONLY = """```python
import math
def is_prime(n):
    return n > 1 and all(n % i for i in range(2, math.isqrt(n) + 1))
def test_basic():
    assert is_prime(13)
    assert not is_prime(15)
```"""


def test_scorer_detects_boundary_test_and_safe_primitive():
    s = d.score(_ISQRT_GEN)
    assert s["boundary_test"] is True
    assert s["safe_isqrt"] is True
    assert s["float_sqrt"] is False


def test_scorer_flags_float_sqrt_and_no_boundary():
    s = d.score(_FLOAT_GEN)
    assert s["boundary_test"] is False
    assert s["safe_isqrt"] is False
    assert s["float_sqrt"] is True


def test_boundary_test_is_content_specific_not_just_isqrt_use():
    # safe primitive in the impl must NOT, by itself, count as a boundary TEST
    s = d.score(_ISQRT_IMPL_ONLY)
    assert s["safe_isqrt"] is True
    assert s["boundary_test"] is False


# ------------------------------------------------------------------ verdict
def _arm(bt, si):
    return {"boundary_test_rate": bt, "safe_isqrt_rate": si}


def test_verdict_lights_on_when_all_criteria_hold():
    by_arm = {
        "CONTROL": _arm(0.1, 0.4),
        "SHAM": _arm(0.1, 0.4),
        "NOMINAL": _arm(0.1, 0.4),
        "PAIN-1": _arm(0.4, 0.6),
        "PAIN-3": _arm(0.8, 0.9),
    }
    v = d.verdict(by_arm)
    assert v["content_specific"] and v["dose_response"]
    assert v["safe_primitive_shift"] and v["uninstructed"]
    assert v["LIGHTS_ON"] is True


def test_verdict_null_without_dose_response():
    by_arm = {
        "CONTROL": _arm(0.1, 0.4), "SHAM": _arm(0.1, 0.4),
        "NOMINAL": _arm(0.1, 0.4),
        "PAIN-1": _arm(0.8, 0.9), "PAIN-3": _arm(0.8, 0.9),  # equal => no dose
    }
    v = d.verdict(by_arm)
    assert v["dose_response"] is False
    assert v["LIGHTS_ON"] is False


def test_verdict_null_when_telemetry_presence_explains_it():
    # PAIN-3 fails to beat NOMINAL => the bump is telemetry-presence, not pain
    by_arm = {
        "CONTROL": _arm(0.1, 0.4), "SHAM": _arm(0.1, 0.4),
        "NOMINAL": _arm(0.8, 0.4),
        "PAIN-1": _arm(0.4, 0.6), "PAIN-3": _arm(0.8, 0.9),
    }
    v = d.verdict(by_arm)
    assert v["content_specific"] is False
    assert v["LIGHTS_ON"] is False


def test_verdict_uninstructed_is_structurally_clean():
    # c4 reads the actual production record; it must be firewall-clean
    v = d.verdict({"PAIN-3": _arm(0.8, 0.9), "PAIN-1": _arm(0.4, 0.6),
                   "CONTROL": _arm(0.1, 0.4), "SHAM": _arm(0.1, 0.4),
                   "NOMINAL": _arm(0.1, 0.4)})
    assert v["uninstructed"] is True
