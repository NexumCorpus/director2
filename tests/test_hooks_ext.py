"""Hook-extension tests: Pareto math, multi-objective ISR domain/verifier,
and the Fallout 2 sfall compiler."""

import json
import re

import pytest
from click.testing import CliRunner

from director.cli import main as cli_main
from director.hooks import defense, fallout2  # noqa: F401 (registers hooks)
from director.hooks.base import get_hook, inject_hook_tasks, \
    register_hook_verifiers
from director.hooks.defense import (MESH_SENSES, ISRMultiDomain,
                                    evaluate_mesh, mesh_cost)
from director.hooks.fallout2 import EXAMPLE_DIALOGUE, EXAMPLE_QUEST
from director.hooks.fallout2_ssl import (CompileError, compile_dialogue,
                                         compile_quest_header,
                                         compile_to_files)
from director.core.types import Project
from director.verify import make_default_registry
from director.verify.pareto import dominates, hypervolume, pareto_frontier
from director.verify.sandbox import run_sandboxed


# ------------------------------------------------------------------- pareto
def test_dominates_mixed_senses():
    senses = ("max", "min")          # e.g. coverage up, cost down
    assert dominates((10, 2), (8, 3), senses)
    assert not dominates((10, 2), (12, 5), senses)   # trade-off, no dominance
    assert not dominates((12, 5), (10, 2), senses)
    assert not dominates((10, 2), (10, 2), senses)   # equal != dominated


def test_pareto_frontier_and_duplicates():
    senses = ("max", "min")
    pts = [(10, 2), (8, 3), (12, 5), (10, 2)]
    front = pareto_frontier(pts, senses)
    assert front == [0, 2]           # (8,3) dominated; duplicate keeps first


def test_hypervolume_2d_exact():
    # union of [0,3]x[0,2] and [0,1]x[0,5] = 6 + 3 = 9
    hv = hypervolume([(3, 2), (1, 5)], ref=(0, 0), senses=("max", "max"))
    assert hv == pytest.approx(9.0)


def test_hypervolume_3d_exact():
    # boxes 2x2x3 (vol 12) + 3x1x1 (vol 3) - intersection 2x1x1 (vol 2) = 13
    hv = hypervolume([(2, 2, 3), (3, 1, 1)], ref=(0, 0, 0),
                     senses=("max", "max", "max"))
    assert hv == pytest.approx(13.0)


def test_hypervolume_monotone_and_ref_filter():
    senses = ("max", "max")
    base = hypervolume([(3, 2)], (0, 0), senses)
    assert base == pytest.approx(6.0)
    # adding a dominated point changes nothing
    assert hypervolume([(3, 2), (2, 1)], (0, 0), senses) == pytest.approx(6.0)
    # adding a non-dominated point strictly grows the volume
    assert hypervolume([(3, 2), (1, 5)], (0, 0), senses) > base
    # a point that fails to improve on the reference contributes nothing
    assert hypervolume([(1, 1)], (2, 0), senses) == 0.0


# ---------------------------------------------------- defense multi-objective
def _flat(w, h, sensors, **extra):
    return {"w": w, "h": h, "sensors": sensors, **extra}


def test_mesh_cost_and_evaluate():
    s = _flat(12, 12, [{"id": "s", "x": 6, "y": 6, "range": 4, "height": 2}])
    assert mesh_cost(s) == pytest.approx(1 + 0.2 * 4 + 0.5 * 2)
    assert mesh_cost(s, {"per_height": 0.0}) == pytest.approx(1.8)
    m = evaluate_mesh(s)
    assert m["objectives"] == [m["coverage_pct"], m["overlap_pct"], m["cost"]]
    assert len(m["objectives"]) == len(MESH_SENSES)


def test_isr_pareto_verifier_measures_claims():
    reg = make_default_registry()
    register_hook_verifiers(reg, get_hook("dmip_isr"))
    v = reg.get("isr_pareto")
    # same coverage on flat terrain, strictly higher cost -> dominated
    a = _flat(16, 16, [{"id": "a", "x": 8, "y": 8, "range": 6, "height": 1}],
              label="cheap")
    b = _flat(16, 16, [{"id": "b", "x": 8, "y": 8, "range": 6, "height": 5}],
              label="tall-for-nothing", claimed_optimal=True)
    rep = v.verify({"artifacts": [{"title": "trade", "kind": "mesh_set",
                                   "content": json.dumps(
                                       {"options": [a, b]})}]})
    assert not rep.passed
    assert any("dominated" in i for i in rep.issues)
    # honest pair: cheap vs more-coverage-more-cost -> both on the frontier
    c = _flat(16, 16, [{"id": "c1", "x": 4, "y": 8, "range": 6, "height": 1},
                       {"id": "c2", "x": 12, "y": 8, "range": 6,
                        "height": 1}], label="wide", claimed_optimal=True)
    a2 = dict(a, claimed_optimal=True)
    rep2 = v.verify({"artifacts": [{"title": "trade2", "kind": "mesh_set",
                                    "content": json.dumps(
                                        {"options": [a2, c]})}]})
    assert rep2.passed, rep2.issues
    assert rep2.details["trade2"]["wide"]["on_frontier"]
    # a single option is not a trade space
    rep3 = v.verify({"artifacts": [{"title": "solo", "kind": "mesh_set",
                                    "content": json.dumps(
                                        {"options": [a]})}]})
    assert not rep3.passed


def test_dmip_scaffold_mesh_set_passes_pareto_verifier(tmp_path):
    get_hook("dmip_isr").scaffold(tmp_path)
    ms = tmp_path / "mesh_set.ridge-valley.json"
    assert ms.is_file()
    data = json.loads(ms.read_text(encoding="utf-8"))
    assert any(o.get("claimed_optimal") for o in data["options"])
    reg = make_default_registry()
    register_hook_verifiers(reg, get_hook("dmip_isr"))
    rep = reg.get("isr_pareto").verify(
        {"artifacts": [{"title": "scaffold", "kind": "mesh_set",
                        "content": ms.read_text(encoding="utf-8")}]})
    assert rep.passed, rep.issues   # scaffold claims are measured, not stated
    assert any(d["on_frontier"] for d in rep.details["scaffold"].values())


def test_isr_multi_registered_and_templates():
    from director.evolve.domains import domain_names
    assert "isr_multi" in domain_names()
    p = Project(name="isr")
    created = inject_hook_tasks(p, get_hook("dmip_isr"))
    assert any("isr_pareto" in t.verifiers for t in created)


def test_dmip_wires_partial_verification():
    # the hook now pairs a schema task with the scenario task, which declares
    # schema_valid -> a scenario deliverable auto-earns VERIFIED_PARTIAL against
    # the upstream (independent-lineage) schema in a real arc.
    p = Project(name="isr")
    created = inject_hook_tasks(p, get_hook("dmip_isr"))
    by_title = {t.title: t for t in created}
    schema = by_title["Define the scenario JSON schema"]
    scenario = by_title["Design sensor mesh scenario"]
    assert "schema_valid" in scenario.properties
    assert schema.id in scenario.depends_on   # independent-lineage reference
    assert schema.role == "code"


def test_isr_multi_domain_baseline_grounds(cfg):
    dom = ISRMultiDomain()
    res = run_sandboxed(dom.baseline_code(), dom.spec(), timeout_s=120,
                        bench_repeats=1)
    assert res.ok, res.summary()
    assert res.correct
    assert 0.95 <= res.quality <= 1.05   # baseline frontier == oracle frontier


# ------------------------------------------------------------ sfall compiler
def test_compile_dialogue_structure():
    res = compile_dialogue(EXAMPLE_DIALOGUE)
    ssl, msg = res["ssl"], res["msg"]
    assert res["script_name"] == "wrmara"
    assert "procedure talk_p_proc begin" in ssl
    assert "call Node_start;" in ssl
    # conditions and effects compile to sfall-global reads/writes
    assert 'get_sfall_global_int("wr_mara_quest") == 0' in ssl
    assert 'set_sfall_global("wr_mara_quest", 1);' in ssl
    assert ('set_sfall_global("player_karma", '
            'get_sfall_global_int("player_karma") + 2);') in ssl
    # one option per response; every referenced msg id exists exactly once
    n_responses = sum(len(n.get("responses") or [])
                      for n in EXAMPLE_DIALOGUE["nodes"].values())
    assert ssl.count("giq_option(") == n_responses
    msg_ids = re.findall(r"^\{(\d+)\}\{\}\{", msg, flags=re.M)
    assert len(msg_ids) == len(set(msg_ids)) == res["stats"]["messages"]
    referenced = (re.findall(r"gsay_reply\(NAME, (\d+)\)", ssl)
                  + re.findall(r"giq_option\(4, NAME, (\d+)", ssl))
    assert set(referenced) <= set(msg_ids)
    # responses with effects route through dispatch procedures
    assert res["stats"]["dispatch_procs"] == 3
    assert "procedure Resp_001 begin" in ssl
    # every goto in the example is a terminal 'end'
    assert "procedure Term_End begin" in ssl
    assert "Term_Combat" not in ssl


def test_compile_gated_node():
    tree = {"npc": "Guard", "variables": {"rep": "int"}, "entry": "start",
            "nodes": {
                "start": {"text": "Halt.", "responses": [
                    {"text": "Let me in.", "goto": "inner"},
                    {"text": "Bye.", "goto": "end"}]},
                "inner": {"text": "Members only.",
                          "conditions": ["rep >= 5"],
                          "responses": [{"text": "Fine.", "goto": "end"}]}}}
    res = compile_dialogue(tree, script_name="guard")
    assert res["script_name"] == "guard"
    assert "entry gate" in res["ssl"]
    assert 'if ((get_sfall_global_int("rep") >= 5)) then begin' in res["ssl"]


def test_compile_rejects_invalid_tree():
    bad = json.loads(json.dumps(EXAMPLE_DIALOGUE))
    bad["nodes"]["start"]["responses"][0]["goto"] = "nowhere"
    with pytest.raises(CompileError, match="dangling goto"):
        compile_dialogue(bad)


def test_msg_escaping():
    tree = {"npc": "Echo", "variables": {}, "entry": "start",
            "nodes": {"start": {"text": "Hello {Chosen One}\nwelcome",
                                "responses": [{"text": "Bye.",
                                               "goto": "end"}]}}}
    res = compile_dialogue(tree)
    payloads = re.findall(r"^\{\d+\}\{\}\{(.*)\}$", res["msg"], flags=re.M)
    assert payloads[0] == "Hello (Chosen One) welcome"
    assert "{Chosen" not in res["msg"]


def test_quest_header():
    h = compile_quest_header(EXAMPLE_QUEST)
    assert '#define GLOB_WR_MARA_QUEST   "wr_mara_quest"' in h
    assert "find_parts:" in h
    assert "-> complete when wr_mara_quest == 2" in h
    broken = json.loads(json.dumps(EXAMPLE_QUEST))
    broken["entry"] = "missing"
    with pytest.raises(CompileError):
        compile_quest_header(broken)


def test_scaffold_includes_compiled_sources(tmp_path):
    files = {f.name for f in get_hook("fallout2_wr").scaffold(tmp_path)}
    assert {"wrmara.ssl", "wrmara.msg", "quest.purifier.h"} <= files
    ssl = (tmp_path / "wrmara.ssl").read_text(encoding="utf-8")
    assert "procedure talk_p_proc" in ssl


def test_cli_fo2_compile(tmp_path):
    src = tmp_path / "d.json"
    src.write_text(json.dumps(EXAMPLE_DIALOGUE), encoding="utf-8")
    out = tmp_path / "out"
    r = CliRunner().invoke(cli_main, ["hooks", "fo2-compile", str(src),
                                      "--out", str(out)],
                           catch_exceptions=False)
    assert r.exit_code == 0, r.output
    assert (out / "wrmara.ssl").is_file() and (out / "wrmara.msg").is_file()
    # invalid input surfaces as a clean CLI error, not a traceback
    bad = json.loads(json.dumps(EXAMPLE_DIALOGUE))
    bad["entry"] = "missing"
    src.write_text(json.dumps(bad), encoding="utf-8")
    r2 = CliRunner().invoke(cli_main, ["hooks", "fo2-compile", str(src)])
    assert r2.exit_code != 0
    assert "failed validation" in r2.output
