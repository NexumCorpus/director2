"""Hook tests: dialogue/quest graph validation, ISR sim correctness, LOS,
discovery-domain grounding, scaffolds, and Director integration."""

import json

from director.hooks import defense, fallout2  # noqa: F401 (registers hooks)
from director.hooks.base import (get_hook, hook_names, inject_hook_tasks,
                                 register_hook_verifiers)
from director.hooks.defense import (EXAMPLE_SCENARIO, ISRPlacementDomain,
                                    _ridge_terrain, coverage_map, simulate)
from director.hooks.fallout2 import (EXAMPLE_DIALOGUE, EXAMPLE_QUEST,
                                     validate_dialogue, validate_quest)
from director.core.types import Project
from director.verify import make_default_registry
from director.verify.sandbox import run_sandboxed


# ------------------------------------------------------------------ fallout 2
def test_example_dialogue_is_valid():
    assert validate_dialogue(EXAMPLE_DIALOGUE) == []


def test_dialogue_catches_dangling_goto_and_unreachable():
    tree = json.loads(json.dumps(EXAMPLE_DIALOGUE))
    tree["nodes"]["start"]["responses"][0]["goto"] = "nowhere"
    problems = validate_dialogue(tree)
    assert any("dangling goto 'nowhere'" in p for p in problems)
    tree2 = json.loads(json.dumps(EXAMPLE_DIALOGUE))
    tree2["nodes"]["orphan"] = {"text": "hi", "responses": [
        {"text": "bye", "goto": "end"}]}
    assert any("unreachable" in p for p in validate_dialogue(tree2))


def test_dialogue_catches_undeclared_variable():
    tree = json.loads(json.dumps(EXAMPLE_DIALOGUE))
    tree["nodes"]["start"]["responses"][1]["conditions"] = ["ghost_var == 1"]
    assert any("undeclared variable 'ghost_var'" in p
               for p in validate_dialogue(tree))


def test_quest_validation():
    assert validate_quest(EXAMPLE_QUEST) == []
    q = json.loads(json.dumps(EXAMPLE_QUEST))
    q["stages"]["return_to_mara"]["transitions"] = []
    problems = validate_quest(q)
    assert any("terminal" in p for p in problems)


def test_fo2_verifier_on_agent_output():
    reg = make_default_registry()
    hook = get_hook("fallout2_wr")
    register_hook_verifiers(reg, hook)
    v = reg.get("fo2_graphs")
    good = {"artifacts": [{"title": "mara", "kind": "dialogue",
                           "content": json.dumps(EXAMPLE_DIALOGUE)}]}
    rep = v.verify(good)
    assert rep.passed and rep.details["artifacts_checked"] == 1
    bad_tree = json.loads(json.dumps(EXAMPLE_DIALOGUE))
    bad_tree["entry"] = "missing"
    bad = {"artifacts": [{"title": "broken", "kind": "dialogue",
                          "content": json.dumps(bad_tree)}]}
    rep2 = v.verify(bad)
    assert not rep2.passed and rep2.issues


# -------------------------------------------------------------------- defense
def test_coverage_basics():
    scenario = {"w": 11, "h": 11,
                "sensors": [{"id": "c", "x": 5, "y": 5, "range": 3}]}
    cov = coverage_map(scenario)
    assert cov[5][5] >= 1          # sensor cell covered
    assert cov[5][8] >= 1          # at range
    assert cov[5][9] == 0          # beyond range
    m = simulate(scenario)
    assert 0 < m["coverage_pct"] < 100
    assert m["overlap_pct"] == 0
    assert m["sensors"] == 1


def test_overlap_and_gap_metrics():
    scenario = {"w": 12, "h": 6, "sensors": [
        {"id": "a", "x": 3, "y": 3, "range": 3},
        {"id": "b", "x": 4, "y": 3, "range": 3}]}
    m = simulate(scenario)
    assert m["overlap_pct"] > 0
    assert m["largest_gap_cells"] > 0


def test_los_blocks_behind_ridge():
    w, h = 24, 16
    terrain = _ridge_terrain(w, h)
    base = {"w": w, "h": h, "terrain": terrain}
    # low sensor north of the ridge cannot see south of it
    low = dict(base, sensors=[{"id": "low", "x": 12, "y": 4, "range": 10,
                               "height": 1}])
    cov_low = coverage_map(low)
    south_covered_low = sum(cov_low[y][x] for y in range(10, 16)
                            for x in range(8, 16))
    # tall mast same spot sees over the ridge
    tall = dict(base, sensors=[{"id": "tall", "x": 12, "y": 4, "range": 10,
                                "height": 8}])
    cov_tall = coverage_map(tall)
    south_covered_tall = sum(cov_tall[y][x] for y in range(10, 16)
                             for x in range(8, 16))
    assert south_covered_tall > south_covered_low


def test_isr_verifier_measures_not_trusts():
    reg = make_default_registry()
    register_hook_verifiers(reg, get_hook("dmip_isr"))
    v = reg.get("isr_coverage")
    # scenario claims target 99% with one tiny sensor -> measured failure
    weak = {"w": 30, "h": 30, "target_pct": 99,
            "sensors": [{"id": "s", "x": 1, "y": 1, "range": 2}]}
    out = {"artifacts": [{"title": "mesh", "kind": "sim",
                          "content": json.dumps(weak)}]}
    rep = v.verify(out)
    assert not rep.passed
    assert any("below declared target" in i for i in rep.issues)


def test_isr_placement_domain_grounds_baseline(cfg):
    dom = ISRPlacementDomain()
    spec = dom.spec()
    res = run_sandboxed(dom.baseline_code(), spec, timeout_s=60,
                        bench_repeats=1)
    assert res.ok, res.summary()
    assert res.correct
    assert 0.95 <= res.quality <= 1.05      # baseline == oracle greedy


# ----------------------------------------------------------------- integration
def test_hook_registry_and_scaffolds(tmp_path):
    assert {"fallout2_wr", "dmip_isr"} <= set(hook_names())
    for name in ("fallout2_wr", "dmip_isr"):
        files = get_hook(name).scaffold(tmp_path / name)
        assert files and all(f.is_file() for f in files)
    # scaffolded dialogue is itself valid
    d = json.loads((tmp_path / "fallout2_wr" / "dialogue.mara.json")
                   .read_text(encoding="utf-8"))
    assert validate_dialogue(d) == []


def test_inject_hook_tasks_into_project():
    p = Project(name="modding")
    hook = get_hook("fallout2_wr")
    created = inject_hook_tasks(p, hook)
    assert len(created) == 4
    # dependency wiring by template index
    by_title = {t.title: t for t in created}
    author = by_title["Author reactive dialogue trees"]
    roster = by_title["Define NPC roster and reactivity matrix"]
    assert roster.id in author.depends_on
    assert "fo2_graphs" in author.verifiers
    # module created and linked
    assert any(m.name == "fallout2_wr work" for m in p.modules.values())


def test_isr_domain_registered_for_evolve():
    from director.evolve.domains import domain_names
    assert "isr_placement" in domain_names()
