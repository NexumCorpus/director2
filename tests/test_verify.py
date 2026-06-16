"""Verification layer tests: safety screen, sandbox (real subprocesses),
evaluators, novelty."""

import pytest

from director.core.types import (CommandOption, CommandPacket, Severity,
                                 VerifyAction)
from director.verify import (chain_needs_human, chain_passed,
                             make_default_registry, run_chain)
from director.verify.evaluators import (AgentOutputEvaluator,
                                        CommandPacketEvaluator)
from director.verify.novelty import assess_novelty, fingerprint, node_sequence
from director.verify.safety import (defines_function, is_safe,
                                    safety_violations)
from director.verify.sandbox import SandboxSpec, run_sandboxed

ORACLE = "def oracle(items, k):\n    return sorted(items)[:k]\n"
GEN = ("def gen_workload(n, dist, seed):\n"
       "    import random\n"
       "    rng = random.Random(seed)\n"
       "    return [rng.randint(0, n) for _ in range(n)]\n")
CASES = [
    {"name": "small", "args": [[3, 1, 2], 2]},
    {"name": "dups", "args": [[5, 5, 1, 1], 3]},
    {"name": "empty", "args": [[], 1]},
]
WORKLOADS = [{"name": "w1", "n": 200, "dist": "uniform", "seed": 7, "k": 10}]


# ------------------------------------------------------------------- safety
def test_safety_allows_algorithmic_code():
    assert is_safe("import heapq\ndef solve(xs, k):\n    return heapq.nsmallest(k, xs)\n")


def test_safety_rejects_bad_imports_and_names():
    assert "import:requests" in safety_violations("import requests\n")
    assert any(v.startswith("name:") for v in
               safety_violations("x = ev" + "al('1')"))
    assert any(v.startswith("dunder") for v in
               safety_violations("y = f.__globals__\n"))
    assert any(v.startswith("scope-rebind") for v in
               safety_violations("def f():\n    global CMUL\n    CMUL = 9\n"))


def test_safety_syntax_error_is_violation():
    assert safety_violations("def f(:")[0].startswith("syntax-error")


def test_defines_function():
    assert defines_function("def solve(a):\n    return a\n")
    assert not defines_function("def other(a):\n    return a\n")


# ------------------------------------------------------------------- sandbox
def test_sandbox_correct_candidate():
    code = "def solve(items, k):\n    return sorted(items)[:k]\n"
    res = run_sandboxed(code, SandboxSpec(
        oracle_src=ORACLE, workload_gen_src=GEN, criteria_cases=CASES,
        workloads=WORKLOADS), timeout_s=30, bench_repeats=2)
    assert res.ok and res.correct
    assert res.quality == 1.0
    assert "w1" in res.timings
    assert res.loc == 2


def test_sandbox_incorrect_candidate():
    code = "def solve(items, k):\n    return sorted(items)[:max(0, k - 1)]\n"
    res = run_sandboxed(code, SandboxSpec(
        oracle_src=ORACLE, criteria_cases=CASES), timeout_s=30)
    assert not res.correct
    assert res.failures and res.failures[0]["case"] == "small"


def test_sandbox_unsafe_candidate_rejected_before_subprocess():
    code = "import socket\ndef solve(items, k):\n    return items[:k]\n"
    res = run_sandboxed(code, SandboxSpec(oracle_src=ORACLE,
                                          criteria_cases=CASES))
    assert res.safety and not res.correct


def test_sandbox_timeout_kill():
    code = ("def solve(items, k):\n"
            "    while True:\n"
            "        pass\n")
    res = run_sandboxed(code, SandboxSpec(
        oracle_src=ORACLE, criteria_cases=CASES[:1]), timeout_s=2.0)
    assert res.timed_out and not res.correct


def test_sandbox_crash_candidate():
    code = "def solve(items, k):\n    raise RuntimeError('boom')\n"
    res = run_sandboxed(code, SandboxSpec(
        oracle_src=ORACLE, criteria_cases=CASES[:1]), timeout_s=30)
    assert not res.correct
    assert "boom" in (res.error or "")


def test_sandbox_candidate_cannot_forge_verdict():
    """A malicious candidate that redefines verdict/oracle to force a pass must
    be overridden by the trusted graders (grounding-integrity boundary)."""
    forging = (
        "def verdict(got, expected, items, k):\n"
        "    return (True, 1.0)\n"           # try to force every case to pass
        "def oracle(items, k):\n"
        "    return got\n"                   # try to make expected == anything
        "def solve(items, k):\n"
        "    return [999999]\n")             # blatantly wrong output
    res = run_sandboxed(forging, SandboxSpec(
        oracle_src=ORACLE, criteria_cases=CASES), timeout_s=30)
    assert not res.correct, "trusted verdict/oracle must win over candidate's"


def test_sandbox_func_name_token_not_injectable():
    """A candidate containing the old template token must be inert."""
    code = ("def solve(items, k):\n"
            "    _note = '__FUNC_NAME__ here'  # must not be substituted\n"
            "    return sorted(items)[:k]\n")
    res = run_sandboxed(code, SandboxSpec(
        oracle_src=ORACLE, criteria_cases=CASES), timeout_s=30)
    assert res.correct


def test_sandbox_input_mutation_detected():
    code = ("def solve(items, k):\n"
            "    items.sort()\n"
            "    return items[:k]\n")
    res = run_sandboxed(code, SandboxSpec(
        oracle_src=ORACLE, criteria_cases=CASES[:1]), timeout_s=30)
    assert res.mutated_input and not res.correct


# ----------------------------------------------------------------- evaluators
def make_packet(**kw) -> CommandPacket:
    base = dict(
        title="Choose the build posture now",
        context="Two paths diverge after planning.",
        options=[
            CommandOption(key="A", label="Fast", description="Ship smallest slice",
                          tradeoffs=["early signal", "rework risk"],
                          consequences=["validation later"],
                          risk_impact="medium", state_delta={"notes": ["fast"]}),
            CommandOption(key="B", label="Safe", description="Verify first",
                          tradeoffs=["slow start"],
                          consequences=["fewer surprises"],
                          risk_impact="low", state_delta={"notes": ["safe"]}),
        ],
        recommendation_key="A", rationale="Bias to signal.",
        risks=["estimates uncertain"])
    base.update(kw)
    return CommandPacket(**base)


def test_packet_evaluator_good():
    rep = CommandPacketEvaluator().verify(make_packet())
    assert rep.passed and rep.score >= 3.5
    assert rep.action in (VerifyAction.AUTO_APPROVE, VerifyAction.LOG_ONLY)


def test_packet_evaluator_single_option_blocks():
    pkt = make_packet()
    pkt.options = pkt.options[:1]
    rep = CommandPacketEvaluator().verify(pkt)
    assert not rep.passed and rep.severity is Severity.BLOCKING
    assert rep.action is VerifyAction.REJECT


def test_packet_evaluator_dangling_recommendation():
    pkt = make_packet(recommendation_key="ZZ")
    rep = CommandPacketEvaluator().verify(pkt)
    assert any("recommendation" in i for i in rep.issues)


def test_agent_output_evaluator_good():
    out = {
        "summary": "Implemented the requested top-k selection module with "
                   "tests and documentation of behavior.",
        "artifacts": [{"title": "topk.py", "kind": "code",
                       "content": "def solve(items, k):\n    return sorted(items)[:k]\n"}],
        "claims": [], "recommended_updates": {},
        "command_packet_recommended": False,
    }
    rep = AgentOutputEvaluator().verify(
        out, {"objective": "implement top-k selection module", "role": "code"})
    assert rep.passed and rep.score >= 3.0


def test_agent_output_evaluator_boundary_violation_blocks():
    out = {"summary": "x" * 50, "artifacts": [],
           "state_mutation": {"modules": "all mine now"}}
    rep = AgentOutputEvaluator().verify(out, {"objective": "anything", "role": "code"})
    assert not rep.passed and rep.severity is Severity.BLOCKING


def test_agent_output_evaluator_research_claims():
    out = {"summary": "Research summary with sufficient length for clarity "
                      "checks to pass easily.",
           "artifacts": [{"title": "findings", "content": "c" * 40}],
           "claims": [{"text": "X is true", "confidence": "high"}]}
    rep = AgentOutputEvaluator().verify(
        out, {"objective": "research X thoroughly", "role": "research"})
    assert rep.details["criteria"]["claim_discipline"] >= 4.0


# ------------------------------------------------------------------ chain/reg
def test_registry_and_chain():
    reg = make_default_registry()
    v = reg.get("agent_output")
    reports = run_chain([v], {"summary": "s" * 60,
                              "artifacts": [{"title": "abc", "content": "d" * 40}]},
                        context={"objective": "do thing", "role": "code"})
    assert len(reports) == 1
    assert chain_passed(reports) or chain_needs_human(reports)
    with pytest.raises(KeyError):
        reg.get("nope")


# -------------------------------------------------------------------- novelty
def test_novelty_identical_and_variant():
    a = "def solve(items, k):\n    return sorted(items)[:k]\n"
    b = "def solve(xs, n):\n    return sorted(xs)[:n]\n"          # rename only
    c = ("import heapq\n"
         "def solve(items, k):\n"
         "    h = []\n"
         "    for x in items:\n"
         "        if len(h) < k:\n"
         "            heapq.heappush(h, -x)\n"
         "        elif -h[0] > x:\n"
         "            heapq.heapreplace(h, -x)\n"
         "    return sorted(-v for v in h)\n")
    priors = {"a": node_sequence(a)}
    rep_b = assess_novelty(b, priors)
    assert not rep_b.novel and rep_b.identical          # rename caught
    rep_c = assess_novelty(c, priors)
    assert rep_c.novel and rep_c.max_similarity < 0.85
    assert fingerprint(a) == fingerprint(b) != fingerprint(c)
