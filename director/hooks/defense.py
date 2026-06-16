"""DMIP defense-tech hook — ISR sensor-coverage mesh modeling.

A small, trusted simulation core (pure Python, deterministic):

* grid scenario with optional terrain heightmap
* sensors with position, range, height
* line-of-sight occlusion (Bresenham over the heightmap)
* coverage / overlap / gap metrics

Plus discovery domains: evolve sensor-PLACEMENT algorithms that beat a greedy
baseline (``isr_placement``), and evolve multi-objective mesh DESIGNERS graded
by hypervolume over (coverage up, cost down) against a greedy frontier
(``isr_multi``) — the RDE pattern applied to ISR mesh design.

The multi-objective layer (``mesh_cost`` / ``evaluate_mesh`` / ``isr_pareto``
verifier) measures coverage, redundancy (cells seen by >= 2 sensors — single
-loss resilience) and cost with trusted code, and rejects any mesh an agent
CLAIMS is Pareto-optimal that measurement says is dominated.

Scenario JSON contract:
{
  "w": 24, "h": 16,
  "terrain": [[0,...], ...]          # optional h rows x w cols heights
  "sensors": [{"id": "s1", "x": 3, "y": 4, "range": 6, "height": 2}, ...]
}
"""

from __future__ import annotations

import json
from pathlib import Path

from ..core.types import Severity, VerificationReport, VerifyAction
from ..verify.pareto import pareto_frontier
from ..verify.sandbox import SandboxSpec
from .base import register_hook


# --------------------------------------------------------------------------- #
# Trusted simulation core
# --------------------------------------------------------------------------- #

def _los_clear(terrain, x0: int, y0: int, h0: float,
               x1: int, y1: int, h1: float) -> bool:
    """Bresenham line-of-sight: blocked if any intermediate cell's terrain
    rises above the interpolated sight line."""
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    steps = max(dx, dy)
    if steps <= 1:
        return True
    for i in range(1, steps):
        t = i / steps
        xi = round(x0 + (x1 - x0) * t)
        yi = round(y0 + (y1 - y0) * t)
        line_h = h0 + (h1 - h0) * t
        if terrain[yi][xi] > line_h:
            return False
    return True


def coverage_map(scenario: dict) -> list[list[int]]:
    """cells -> number of sensors covering them (range + LOS)."""
    w, h = int(scenario["w"]), int(scenario["h"])
    terrain = scenario.get("terrain") or [[0] * w for _ in range(h)]
    cov = [[0] * w for _ in range(h)]
    for s in scenario.get("sensors", []):
        sx, sy = int(s["x"]), int(s["y"])
        if not (0 <= sx < w and 0 <= sy < h):
            continue
        rng = float(s.get("range", 5))
        s_h = terrain[sy][sx] + float(s.get("height", 1.0))
        r2 = rng * rng
        for y in range(max(0, int(sy - rng)), min(h, int(sy + rng) + 1)):
            for x in range(max(0, int(sx - rng)), min(w, int(sx + rng) + 1)):
                if (x - sx) ** 2 + (y - sy) ** 2 > r2:
                    continue
                if _los_clear(terrain, sx, sy, s_h, x, y,
                              terrain[y][x] + 0.5):
                    cov[y][x] += 1
    return cov


def simulate(scenario: dict) -> dict:
    """Trusted metrics for one scenario."""
    w, h = int(scenario["w"]), int(scenario["h"])
    cov = coverage_map(scenario)
    cells = w * h
    covered = sum(1 for row in cov for c in row if c >= 1)
    overlap = sum(1 for row in cov for c in row if c >= 2)
    # largest contiguous uncovered gap (4-connected flood fill)
    seen = [[False] * w for _ in range(h)]
    largest_gap = 0
    for y in range(h):
        for x in range(w):
            if cov[y][x] >= 1 or seen[y][x]:
                continue
            size = 0
            stack = [(x, y)]
            seen[y][x] = True
            while stack:
                cx, cy = stack.pop()
                size += 1
                for nx, ny in ((cx + 1, cy), (cx - 1, cy),
                               (cx, cy + 1), (cx, cy - 1)):
                    if 0 <= nx < w and 0 <= ny < h and not seen[ny][nx] \
                            and cov[ny][nx] == 0:
                        seen[ny][nx] = True
                        stack.append((nx, ny))
            largest_gap = max(largest_gap, size)
    n_sensors = len(scenario.get("sensors", []))
    return {
        "cells": cells,
        "coverage_pct": round(100.0 * covered / cells, 2) if cells else 0.0,
        "overlap_pct": round(100.0 * overlap / cells, 2) if cells else 0.0,
        "largest_gap_cells": largest_gap,
        "sensors": n_sensors,
        "cells_per_sensor": round(covered / n_sensors, 2) if n_sensors else 0.0,
    }


# --------------------------------------------------------------------------- #
# Multi-objective layer: cost model + trusted Pareto evaluation
# --------------------------------------------------------------------------- #

DEFAULT_COST_MODEL = {"base": 1.0, "per_range": 0.2, "per_height": 0.5}

#: objective directions for evaluate_mesh()["objectives"]
MESH_SENSES = ("max", "max", "min")     # coverage_pct, redundancy_pct, cost


def mesh_cost(scenario: dict, cost_model: dict | None = None) -> float:
    """Deterministic mesh cost: per sensor, base + range + mast height."""
    cm = {**DEFAULT_COST_MODEL, **(cost_model or {})}
    total = 0.0
    for s in scenario.get("sensors", []):
        total += (cm["base"] + cm["per_range"] * float(s.get("range", 5))
                  + cm["per_height"] * float(s.get("height", 1.0)))
    return round(total, 4)


def evaluate_mesh(scenario: dict, cost_model: dict | None = None) -> dict:
    """:func:`simulate` metrics plus cost and the objective tuple used for
    Pareto math. Redundancy = % of cells seen by >= 2 sensors (resilience to
    a single sensor loss), so it is maximized alongside coverage."""
    m = simulate(scenario)
    m["cost"] = mesh_cost(scenario, cost_model)
    m["objectives"] = [m["coverage_pct"], m["overlap_pct"], m["cost"]]
    return m


# --------------------------------------------------------------------------- #
# Verifier: simulation artifacts must meet declared coverage targets
# --------------------------------------------------------------------------- #

class _CoverageVerifier:
    """Checks artifacts of kind='sim' (scenario JSON, optional 'target_pct').
    The metric is computed by trusted code here — never taken from the agent."""
    name = "isr_coverage"

    def verify(self, target, context=None) -> VerificationReport:
        problems: list[str] = []
        details: dict = {}
        checked = 0
        artifacts = (target or {}).get("artifacts", []) \
            if isinstance(target, dict) else []
        for a in artifacts:
            if not isinstance(a, dict) or str(a.get("kind")) != "sim":
                continue
            checked += 1
            try:
                scenario = json.loads(str(a.get("content", "")))
            except json.JSONDecodeError as exc:
                problems.append(f"artifact '{a.get('title')}': not JSON ({exc})")
                continue
            if "w" not in scenario or "h" not in scenario:
                problems.append(f"artifact '{a.get('title')}': missing w/h")
                continue
            metrics = simulate(scenario)
            details[str(a.get("title"))] = metrics
            target_pct = float(scenario.get("target_pct", 0))
            if target_pct and metrics["coverage_pct"] < target_pct:
                problems.append(
                    f"artifact '{a.get('title')}': measured coverage "
                    f"{metrics['coverage_pct']}% below declared target "
                    f"{target_pct}%")
        if checked == 0:
            return VerificationReport(
                verifier=self.name, passed=True, score=3.0,
                severity=Severity.INFO, action=VerifyAction.LOG_ONLY,
                issues=["no sim artifacts to verify"])
        passed = not problems
        return VerificationReport(
            verifier=self.name, passed=passed,
            score=5.0 if passed else 2.0,
            severity=Severity.INFO if passed else Severity.MAJOR,
            action=VerifyAction.AUTO_APPROVE if passed
            else VerifyAction.REQUIRE_HUMAN_REVIEW,
            issues=problems[:10], details=details)


class _ParetoVerifier:
    """Checks artifacts of kind='mesh_set': JSON ``{"options": [scenario,..]}``
    where each option is a full scenario plus optional ``label`` and
    ``claimed_optimal``. Objectives are MEASURED here (coverage, redundancy,
    cost); a dominated option claimed optimal fails the artifact."""
    name = "isr_pareto"

    def verify(self, target, context=None) -> VerificationReport:
        problems: list[str] = []
        details: dict = {}
        checked = 0
        artifacts = (target or {}).get("artifacts", []) \
            if isinstance(target, dict) else []
        for a in artifacts:
            if not isinstance(a, dict) or str(a.get("kind")) != "mesh_set":
                continue
            checked += 1
            title = str(a.get("title"))
            try:
                data = json.loads(str(a.get("content", "")))
            except json.JSONDecodeError as exc:
                problems.append(f"artifact '{title}': not JSON ({exc})")
                continue
            options = data.get("options") if isinstance(data, dict) else None
            if not isinstance(options, list) or len(options) < 2:
                problems.append(f"artifact '{title}': mesh_set needs >= 2 "
                                f"options to compare")
                continue
            evals, bad = [], False
            for i, opt in enumerate(options):
                if not isinstance(opt, dict) or "w" not in opt or "h" not in opt:
                    problems.append(f"artifact '{title}' option[{i}]: "
                                    f"missing w/h")
                    bad = True
                    break
                evals.append(evaluate_mesh(opt))
            if bad:
                continue
            objs = [e["objectives"] for e in evals]
            front = set(pareto_frontier(objs, MESH_SENSES))
            labels = [str(o.get("label", f"option_{i}"))
                      for i, o in enumerate(options)]
            details[title] = {
                labels[i]: {"objectives": objs[i], "on_frontier": i in front}
                for i in range(len(options))}
            for i, opt in enumerate(options):
                if opt.get("claimed_optimal") and i not in front:
                    problems.append(
                        f"artifact '{title}': option '{labels[i]}' claimed "
                        f"optimal but measurement says it is dominated "
                        f"(or a duplicate)")
        if checked == 0:
            return VerificationReport(
                verifier=self.name, passed=True, score=3.0,
                severity=Severity.INFO, action=VerifyAction.LOG_ONLY,
                issues=["no mesh_set artifacts to verify"])
        passed = not problems
        return VerificationReport(
            verifier=self.name, passed=passed,
            score=5.0 if passed else 2.0,
            severity=Severity.INFO if passed else Severity.MAJOR,
            action=VerifyAction.AUTO_APPROVE if passed
            else VerifyAction.REQUIRE_HUMAN_REVIEW,
            issues=problems[:10], details=details)


# --------------------------------------------------------------------------- #
# Discovery domain: evolve placement algorithms vs greedy baseline
# --------------------------------------------------------------------------- #

# The oracle/verdict run INSIDE the sandbox, so they are self-contained source.
_PLACEMENT_COMMON = '''\
def _cov_count(w, h, placements, rng_):
    covered = set()
    r2 = rng_ * rng_
    for (sx, sy) in placements:
        for y in range(max(0, int(sy - rng_)), min(h, int(sy + rng_) + 1)):
            for x in range(max(0, int(sx - rng_)), min(w, int(sx + rng_) + 1)):
                if (x - sx) ** 2 + (y - sy) ** 2 <= r2:
                    covered.add((x, y))
    return len(covered)
'''

_PLACEMENT_ORACLE = _PLACEMENT_COMMON + '''\

def oracle(scenario, k):
    """Greedy max-coverage placement on a coarse grid (trusted baseline)."""
    w, h, rng_ = scenario["w"], scenario["h"], scenario["range"]
    placements = []
    step = max(1, int(rng_ // 2))
    cand = [(x, y) for y in range(0, h, step) for x in range(0, w, step)]
    for _ in range(k):
        best, best_gain = None, -1
        base = _cov_count(w, h, placements, rng_)
        for c in cand:
            if c in placements:
                continue
            gain = _cov_count(w, h, placements + [c], rng_) - base
            if gain > best_gain:
                best, best_gain = c, gain
        if best is None:
            break
        placements.append(best)
    return placements
'''

_PLACEMENT_GEN = '''\
def gen_workload(n, dist, seed):
    import random
    rng = random.Random(seed)
    if dist == "wide":
        w, h = 30, 12
    elif dist == "tall":
        w, h = 12, 30
    else:
        w, h = 20, 20
    return {"w": w, "h": h, "range": rng.choice([4, 5, 6])}
'''

_PLACEMENT_VERDICT = _PLACEMENT_COMMON + '''\

def verdict(got, expected, scenario, k):
    w, h, rng_ = scenario["w"], scenario["h"], scenario["range"]
    if not isinstance(got, list) or len(got) > k:
        return (False, 0.0)
    placements = []
    for p in got:
        try:
            x, y = int(p[0]), int(p[1])
        except (TypeError, ValueError, IndexError):
            return (False, 0.0)
        if not (0 <= x < w and 0 <= y < h):
            return (False, 0.0)
        placements.append((x, y))
    cand_cov = _cov_count(w, h, placements, rng_)
    orc_cov = max(1, _cov_count(w, h, [(int(p[0]), int(p[1]))
                                        for p in expected], rng_))
    q = cand_cov / orc_cov
    return (q >= 0.5, min(q, 1.25))
'''


class ISRPlacementDomain:
    """solve(scenario, k) -> list of [x, y] sensor positions. Quality =
    covered cells vs greedy oracle (computed by trusted code, capped 1.25 so
    beating greedy is rewarded but bounded)."""
    name = "isr_placement"

    def describe(self) -> str:
        return (
            "PROBLEM: ISR sensor placement. Implement solve(scenario, k) "
            "where scenario = {'w': int, 'h': int, 'range': number}. Return "
            "a list of up to k [x, y] integer positions (0<=x<w, 0<=y<h) for "
            "omnidirectional sensors of the given range, maximizing the "
            "number of distinct grid cells within euclidean range of at "
            "least one sensor. Spread matters: overlapping sensors waste "
            "coverage. Deterministic algorithms only (no randomness without "
            "a fixed seed).")

    def baseline_code(self) -> str | None:
        # Same greedy as the oracle -> quality 1.0 reference.
        return _PLACEMENT_COMMON + (
            "\n"
            "def solve(scenario, k):\n"
            "    w, h, rng_ = scenario['w'], scenario['h'], scenario['range']\n"
            "    placements = []\n"
            "    step = max(1, int(rng_ // 2))\n"
            "    cand = [(x, y) for y in range(0, h, step)\n"
            "            for x in range(0, w, step)]\n"
            "    for _ in range(k):\n"
            "        best, best_gain = None, -1\n"
            "        base = _cov_count(w, h, placements, rng_)\n"
            "        for c in cand:\n"
            "            if c in placements:\n"
            "                continue\n"
            "            gain = _cov_count(w, h, placements + [c], rng_) - base\n"
            "            if gain > best_gain:\n"
            "                best, best_gain = c, gain\n"
            "        if best is None:\n"
            "            break\n"
            "        placements.append(best)\n"
            "    return [list(p) for p in placements]\n")

    def spec(self) -> SandboxSpec:
        return SandboxSpec(
            oracle_src=_PLACEMENT_ORACLE,
            workload_gen_src=_PLACEMENT_GEN,
            verdict_src=_PLACEMENT_VERDICT,
            criteria_cases=[
                {"name": "tiny", "args": [{"w": 10, "h": 8, "range": 4}, 2]},
                {"name": "square", "args": [{"w": 16, "h": 16, "range": 5}, 3]},
            ],
            workloads=[
                {"name": "square_20", "n": 0, "dist": "square", "seed": 5, "k": 4},
                {"name": "wide_30", "n": 0, "dist": "wide", "seed": 6, "k": 4},
            ],
            func_name="solve")


# --------------------------------------------------------------------------- #
# Discovery domain: multi-objective mesh design (hypervolume vs greedy)
# --------------------------------------------------------------------------- #

# Self-contained sandbox sources. Sensor tiers trade range against cost, so
# the trade-off is real: many cheap short masts vs few expensive long ones.
_MULTI_COMMON = '''\
TIERS = {1: (0.75, 1.0), 2: (1.0, 2.0), 3: (1.4, 4.0)}  # range mult, cost

def _obj(scenario, mesh):
    """(covered_cells, total_cost) for one mesh = list of [x, y, tier]."""
    w, h, base = scenario["w"], scenario["h"], scenario["range"]
    covered = set()
    cost = 0.0
    for (sx, sy, tier) in mesh:
        mult, c = TIERS[tier]
        cost += c
        rng_ = base * mult
        r2 = rng_ * rng_
        for y in range(max(0, int(sy - rng_)), min(h, int(sy + rng_) + 1)):
            for x in range(max(0, int(sx - rng_)), min(w, int(sx + rng_) + 1)):
                if (x - sx) ** 2 + (y - sy) ** 2 <= r2:
                    covered.add((x, y))
    return (len(covered), cost)
'''

_MULTI_GREEDY = '''\

def _greedy_mesh(scenario, budget, tiers):
    """Cost-efficiency greedy: each pick maximizes new-cells-per-cost."""
    w, h, base = scenario["w"], scenario["h"], scenario["range"]
    step = max(1, int(base // 2))
    cand = [(x, y) for y in range(0, h, step) for x in range(0, w, step)]
    mesh = []
    covered = set()
    for _ in range(budget):
        best, best_eff, best_cells = None, 0.0, None
        for (cx, cy) in cand:
            for tier in tiers:
                mult, c = TIERS[tier]
                rng_ = base * mult
                r2 = rng_ * rng_
                cells = []
                for y in range(max(0, int(cy - rng_)),
                               min(h, int(cy + rng_) + 1)):
                    for x in range(max(0, int(cx - rng_)),
                                   min(w, int(cx + rng_) + 1)):
                        if (x - cx) ** 2 + (y - cy) ** 2 <= r2 \\
                                and (x, y) not in covered:
                            cells.append((x, y))
                eff = len(cells) / c
                if eff > best_eff:
                    best, best_eff, best_cells = [cx, cy, tier], eff, cells
        if best is None:
            break
        mesh.append(best)
        covered.update(best_cells)
    return mesh

def _greedy_frontier(scenario, k):
    """Three reference designs: cheap / balanced / max-coverage."""
    return [_greedy_mesh(scenario, max(1, k // 2), (1,)),
            _greedy_mesh(scenario, k, (1, 2, 3)),
            _greedy_mesh(scenario, k, (3,))]
'''

_MULTI_ORACLE = _MULTI_COMMON + _MULTI_GREEDY + '''\

def oracle(scenario, k):
    return _greedy_frontier(scenario, k)
'''

_MULTI_GEN = '''\
def gen_workload(n, dist, seed):
    import random
    rng = random.Random(seed)
    if dist == "wide":
        w, h = 30, 12
    elif dist == "compact":
        w, h = 14, 14
    else:
        w, h = 22, 18
    return {"w": w, "h": h, "range": rng.choice([4, 5, 6])}
'''

_MULTI_VERDICT = _MULTI_COMMON + '''\

def _frontier_hv(meshes, scenario, k):
    """2D hypervolume of the option set, oriented to maximization:
    x = covered cells, y = cost slack vs worst possible (k tier-3 masts)."""
    ref_cost = 4.0 * k + 1.0
    pts = []
    for mesh in meshes:
        covered, cost = _obj(scenario, mesh)
        if covered > 0 and cost < ref_cost:
            pts.append((float(covered), ref_cost - cost))
    hv, y_best = 0.0, 0.0
    for x, y in sorted(pts, key=lambda p: (-p[0], -p[1])):
        if y > y_best:
            hv += x * (y - y_best)
            y_best = y
    return hv

def verdict(got, expected, scenario, k):
    w, h = scenario["w"], scenario["h"]
    if not isinstance(got, list) or not (1 <= len(got) <= 3):
        return (False, 0.0)
    cleaned = []
    for mesh in got:
        if not isinstance(mesh, list) or not (1 <= len(mesh) <= k):
            return (False, 0.0)
        cm = []
        for p in mesh:
            try:
                x, y, tier = int(p[0]), int(p[1]), int(p[2])
            except (TypeError, ValueError, IndexError):
                return (False, 0.0)
            if not (0 <= x < w and 0 <= y < h) or tier not in TIERS:
                return (False, 0.0)
            cm.append([x, y, tier])
        cleaned.append(cm)
    hv_got = _frontier_hv(cleaned, scenario, k)
    hv_orc = _frontier_hv(expected, scenario, k)
    if hv_orc <= 0:
        return (hv_got > 0, 1.0 if hv_got > 0 else 0.0)
    q = hv_got / hv_orc
    return (q >= 0.6, min(q, 1.25))
'''


class ISRMultiDomain:
    """solve(scenario, k) -> 1-3 alternative mesh designs, each a list of up
    to k [x, y, tier] entries. Graded by 2D hypervolume (coverage up, cost
    down) of the design set vs a greedy three-budget frontier — trusted code
    computes everything; beating greedy is rewarded but capped at 1.25."""
    name = "isr_multi"

    def describe(self) -> str:
        return (
            "PROBLEM: multi-objective ISR mesh design. Implement "
            "solve(scenario, k) where scenario = {'w': int, 'h': int, "
            "'range': number}. Sensors come in tiers: tier 1 = 0.75x base "
            "range, cost 1; tier 2 = 1.0x, cost 2; tier 3 = 1.4x, cost 4. "
            "Return a list of 1-3 ALTERNATIVE mesh designs (a mini Pareto "
            "frontier, e.g. cheap / balanced / max-coverage). Each design is "
            "a list of up to k [x, y, tier] entries with 0<=x<w, 0<=y<h, "
            "tier in {1,2,3}. Score = hypervolume of your designs in "
            "(covered cells UP, total cost DOWN) versus a greedy baseline "
            "frontier; spreading sensors and spending cost only where it "
            "buys coverage both matter. Deterministic algorithms only.")

    def baseline_code(self) -> str | None:
        # Same greedy frontier as the oracle -> hypervolume ratio 1.0.
        return _MULTI_COMMON + _MULTI_GREEDY + (
            "\n"
            "def solve(scenario, k):\n"
            "    return _greedy_frontier(scenario, k)\n")

    def spec(self) -> SandboxSpec:
        return SandboxSpec(
            oracle_src=_MULTI_ORACLE,
            workload_gen_src=_MULTI_GEN,
            verdict_src=_MULTI_VERDICT,
            criteria_cases=[
                {"name": "tiny", "args": [{"w": 10, "h": 8, "range": 4}, 2]},
                {"name": "mid", "args": [{"w": 16, "h": 12, "range": 5}, 3]},
            ],
            workloads=[
                {"name": "square_22", "n": 0, "dist": "square", "seed": 7,
                 "k": 4},
                {"name": "wide_30", "n": 0, "dist": "wide", "seed": 8,
                 "k": 4},
            ],
            func_name="solve")


# --------------------------------------------------------------------------- #
# Scaffold + hook
# --------------------------------------------------------------------------- #

EXAMPLE_SCENARIO = {
    "name": "ridge-valley ISR mesh",
    "w": 24, "h": 16,
    "target_pct": 70,
    "terrain": None,   # filled by scaffold with a ridge
    "sensors": [
        {"id": "north-mast", "x": 6, "y": 3, "range": 6, "height": 3},
        {"id": "south-mast", "x": 16, "y": 12, "range": 6, "height": 3},
        {"id": "valley-relay", "x": 12, "y": 8, "range": 4, "height": 1},
    ],
}


def _ridge_terrain(w: int, h: int) -> list[list[int]]:
    terrain = [[0] * w for _ in range(h)]
    ridge_y = h // 2
    for x in range(w // 3, 2 * w // 3):
        terrain[ridge_y][x] = 4
        if ridge_y + 1 < h:
            terrain[ridge_y + 1][x] = 3
    return terrain


class DefenseHook:
    name = "dmip_isr"
    description = ("DMIP defense-tech: ISR sensor-coverage mesh modeling, "
                   "trusted coverage/LOS simulation, and a placement "
                   "discovery domain for the improvement loop.")

    def task_templates(self) -> list[dict]:
        return [
            {"title": "Define ISR scenario and requirements", "role": "research",
             "objective": "Define the operating area, terrain features, "
                          "threat axes, and coverage requirements for the ISR "
                          "mesh. Produce a requirements artifact with "
                          "measurable targets (coverage %, max gap size).",
             "acceptance_criteria": ["coverage target stated as a number",
                                     "terrain and threat assumptions explicit"]},
            {"title": "Define the scenario JSON schema", "role": "code",
             "depends_on_index": [0],
             "objective": "Produce a draft-07 JSON Schema artifact (kind='code') "
                          "for the scenario contract, with VALUE constraints "
                          "(not just types): top-level type 'object', required "
                          "[w,h,sensors]; w/h integer with minimum 1 and a "
                          "maximum; sensors array with minItems 1, items object "
                          "required [id,x,y,range] where id is a string with a "
                          "pattern, x/y/range/height numbers with minimum 0; "
                          "optional target_pct number 0-100. The value "
                          "constraints are what let the downstream scenario be "
                          "partially VERIFIED against this schema by trusted "
                          "code (a shape-only schema cannot).",
             "acceptance_criteria": ["valid JSON Schema with value constraints",
                                     "covers w/h/sensors/target_pct"]},
            {"title": "Design sensor mesh scenario", "role": "code",
             "depends_on_index": [0, 1],
             "objective": "Produce a scenario JSON artifact (kind='sim') per "
                          "the contract: w, h, optional terrain heightmap, "
                          "sensors[{id,x,y,range,height}], and target_pct. "
                          "It will be (a) MEASURED for coverage by the trusted "
                          "isr_coverage verifier and (b) structurally "
                          "VERIFIED_PARTIAL against the upstream schema by "
                          "trusted code - conform to the schema and place "
                          "sensors to meet target_pct.",
             "acceptance_criteria": ["measured coverage meets target_pct",
                                     "validates against the scenario schema"],
             "verifiers": ["isr_coverage"],
             "properties": ["schema_valid"],
             "context": "Scenario JSON contract example:\n" +
                        json.dumps({k: v for k, v in EXAMPLE_SCENARIO.items()
                                    if k != "terrain"}, indent=1)},
            {"title": "Red-team the mesh", "role": "review",
             "depends_on_index": [2],
             "objective": "Attack the proposed mesh: single-point failures, "
                          "terrain-masked approach corridors, sensor loss "
                          "degradation. Raise risks[] for each finding."},
            {"title": "Simulate degraded modes", "role": "simulation",
             "depends_on_index": [2],
             "objective": "Model sensor-loss scenarios (each sensor failing "
                          "alone) and report coverage degradation per loss, "
                          "with the assumption set stated."},
            {"title": "Map the coverage-cost trade space", "role": "code",
             "depends_on_index": [2],
             "objective": "Produce a mesh_set artifact (kind='mesh_set'): "
                          "JSON {'options': [scenario, ...]} with 2+ "
                          "alternative meshes spanning cheap to gold-plated, "
                          "each with a 'label'. Mark designs you believe "
                          "Pareto-optimal with claimed_optimal: true — the "
                          "isr_pareto verifier MEASURES coverage, redundancy "
                          "and cost and fails any dominated claim.",
             "acceptance_criteria": ["2+ labeled options",
                                     "optimality claims survive measurement"],
             "verifiers": ["isr_pareto"]},
        ]

    def verifiers(self) -> dict:
        return {"isr_coverage": _CoverageVerifier,
                "isr_pareto": _ParetoVerifier}

    def scaffold(self, target_dir, **params) -> list[Path]:
        target = Path(target_dir)
        target.mkdir(parents=True, exist_ok=True)
        scenario = dict(EXAMPLE_SCENARIO)
        scenario["terrain"] = _ridge_terrain(scenario["w"], scenario["h"])
        p = target / "scenario.ridge-valley.json"
        p.write_text(json.dumps(scenario, indent=2), encoding="utf-8")
        metrics = simulate(scenario)
        m = target / "scenario.ridge-valley.metrics.json"
        m.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

        # trade-space example: three variants of the same mesh, with
        # frontier membership MEASURED (the isr_pareto verifier pattern)
        budget = json.loads(json.dumps(scenario))
        for s in budget["sensors"]:
            s["height"] = 1
            s["range"] = max(3, s["range"] - 2)
        budget["label"] = "budget"
        balanced = json.loads(json.dumps(scenario))
        balanced["label"] = "as-designed"
        gold = json.loads(json.dumps(scenario))
        for s in gold["sensors"]:
            s["height"] = s.get("height", 1) + 4
            s["range"] = s["range"] + 2
        gold["label"] = "gold-plated"
        options = [budget, balanced, gold]
        objs = [evaluate_mesh(o)["objectives"] for o in options]
        front = set(pareto_frontier(objs, MESH_SENSES))
        for i, o in enumerate(options):
            o["claimed_optimal"] = i in front
        ms = target / "mesh_set.ridge-valley.json"
        ms.write_text(json.dumps({"options": options}, indent=2),
                      encoding="utf-8")
        msm = target / "mesh_set.ridge-valley.metrics.json"
        msm.write_text(json.dumps(
            {o["label"]: {"objectives": objs[i], "on_frontier": i in front}
             for i, o in enumerate(options)}, indent=2), encoding="utf-8")

        readme = target / "README-dmip-isr.md"
        readme.write_text(
            "# DMIP ISR mesh pack\n\n"
            "Generated by Director 2.0 `dmip_isr` hook.\n\n"
            f"Example scenario measured: {metrics['coverage_pct']}% coverage, "
            f"largest gap {metrics['largest_gap_cells']} cells.\n\n"
            "- `scenario.*.json` — mesh scenarios (trusted sim: range + "
            "Bresenham LOS over terrain)\n"
            "- `mesh_set.*.json` — coverage/redundancy/cost trade space; "
            "frontier membership is measured, never claimed\n"
            "- run `director evolve run isr_placement` to evolve placement "
            "algorithms against the greedy baseline\n"
            "- run `director evolve run isr_multi` to evolve multi-objective "
            "mesh designers graded by hypervolume\n", encoding="utf-8")
        return [p, m, ms, msm, readme]


register_hook(DefenseHook)

# register the discovery domains with the evolve registry
from ..evolve.domains import register_domain                    # noqa: E402
register_domain("isr_placement", ISRPlacementDomain)
register_domain("isr_multi", ISRMultiDomain)
