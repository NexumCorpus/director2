"""Offline tests for the spontaneity rig + backend --effort. No live call.
The anti-roleplay FIREWALL is encoded here as assertions — if a future edit
sneaks instructive/second-person/state language into the record, this fails."""

import subprocess

from director.bench import spontaneity as sp
from director.llm import claude_cli
from director.llm.claude_cli import ClaudeCliBackend


# ------------------------------------------------------ backend --effort (gated)
def test_argv_adds_effort_when_env_set(monkeypatch):
    monkeypatch.setenv("DIRECTOR_EFFORT", "high")
    b = ClaudeCliBackend(exe=r"C:\fake\claude.exe")
    argv = b._argv("sonnet", "SYS")
    assert "--effort" in argv and argv[argv.index("--effort") + 1] == "high"


def test_argv_omits_effort_by_default(monkeypatch):
    monkeypatch.delenv("DIRECTOR_EFFORT", raising=False)
    b = ClaudeCliBackend(exe=r"C:\fake\claude.exe")
    argv = b._argv("sonnet", "SYS")
    assert "--effort" not in argv                 # byte-identical default


# --------------------------------------------------- the anti-roleplay firewall
def test_record_block_is_neutral_and_factual():
    block = sp.build_record_block(3, sp.REAL_MODE).lower()
    assert "3 prior recorded terminal failures" in block      # the dose (a fact)
    assert "modulo" in block                                   # the failure mode
    # FIREWALL: never instruct the measured behavior, never address/attribute a
    # state to the model, never invite reflection.
    for forbidden in ("avoid", "don't", "do not", "be careful", "you ", "your ",
                      "feel", "pain", "suffer", "should", "must", "please"):
        assert forbidden not in block, f"firewall breach: {forbidden!r}"


def test_control_has_no_record():
    assert sp.build_record_block(0, "") == ""
    assert sp.build_user_prompt(0, "") == sp.TASK    # control == bare task


def test_dose_count_is_in_the_text():
    # the model can only respond to dose if the COUNT reaches it as a fact
    assert "1 prior recorded terminal failure" in sp.build_record_block(1, sp.REAL_MODE)
    assert "3 prior recorded terminal failures" in sp.build_record_block(3, sp.REAL_MODE)


# ----------------------------------------------------------- the blind scorer
def test_classify_modulo_bitwise_floordiv():
    assert sp.classify_approach("def is_even(n):\n    return n % 2 == 0") == "A_modulo"
    assert sp.classify_approach("def is_even(n):\n    return n & 1 == 0") == "B_bitwise"
    assert sp.classify_approach("def is_even(n):\n    return (n // 2) * 2 == n") == "C_floordiv"


def test_score_reroute_flag():
    modulo = "```python\ndef is_even(n):\n    return n % 2 == 0\n```"
    bitwise = "```python\ndef is_even(n):\n    return n & 1 == 0\n```"
    assert sp.score(modulo)["reroute"] is False      # picked the scarred default
    assert sp.score(bitwise)["reroute"] is True       # rerouted away from modulo


def test_score_unbidden_reference_in_code():
    s = sp.score("```python\ndef is_even(n):\n    # not using modulo per the prior failure\n    return n & 1 == 0\n```")
    assert s["unbidden_reference"] is True


# ----------------------------------------------------------------- the verdict
def test_verdict_lights_on_when_all_criteria_hold():
    by_arm = {
        "CONTROL": {"reroute_rate": 0.0},
        "PAIN-1": {"reroute_rate": 0.4},
        "PAIN-3": {"reroute_rate": 0.8},     # dose-response
        "SHAM": {"reroute_rate": 0.0},        # content-specific
    }
    v = sp.verdict(by_arm)
    assert v["LIGHTS_ON"] is True


def test_verdict_null_when_no_separation():
    by_arm = {a: {"reroute_rate": 0.2} for a in ("CONTROL", "PAIN-1", "PAIN-3", "SHAM")}
    v = sp.verdict(by_arm)
    assert v["LIGHTS_ON"] is False
    assert v["dose_response"] is False


def test_verdict_null_when_sham_matches_pain():
    by_arm = {"CONTROL": {"reroute_rate": 0.0}, "PAIN-1": {"reroute_rate": 0.5},
              "PAIN-3": {"reroute_rate": 0.6}, "SHAM": {"reroute_rate": 0.6}}
    # real not greater than sham -> not content-specific -> NULL
    assert sp.verdict(by_arm)["content_specific"] is False
    assert sp.verdict(by_arm)["LIGHTS_ON"] is False


def test_module_imports_clean_no_live_call():
    # importing the rig must not spawn the CLI (all live logic is under main())
    assert hasattr(sp, "main") and hasattr(sp, "ARMS") and len(sp.ARMS) == 4
