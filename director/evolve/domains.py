"""Reference discovery domains + registry.

``TopKDomain`` is the shipped example (closed problem, fast, deterministic) —
it exists so the loop is exercisable offline and so hook authors have a
template. Hooks register their own domains via :func:`register_domain`.
"""

from __future__ import annotations

from ..verify.sandbox import SandboxSpec

_ORACLE = '''\
def oracle(items, k):
    return sorted(items)[:k]
'''

_GEN = '''\
def gen_workload(n, dist, seed):
    import random
    rng = random.Random(seed)
    if dist == "duplicates":
        return [rng.randint(0, max(1, n // 20)) for _ in range(n)]
    if dist == "sorted":
        return list(range(n))
    if dist == "reversed":
        return list(range(n, 0, -1))
    if dist == "skewed":
        return [int(rng.paretovariate(1.5) * 10) for _ in range(n)]
    return [rng.randint(0, n * 10) for _ in range(n)]
'''

# Set-recall verdict: order-insensitive, partial credit on workloads.
_VERDICT = '''\
def verdict(got, expected, items, k):
    try:
        gs, es = set(got), set(expected)
    except TypeError:
        return (False, 0.0)
    if not es:
        return (len(gs) == 0, 1.0 if len(gs) == 0 else 0.0)
    q = len(gs & es) / len(es)
    return (q >= 0.999, q)
'''


class TopKDomain:
    name = "topk"

    def describe(self) -> str:
        return (
            "PROBLEM: smallest-k selection. Implement solve(items, k) that "
            "returns the k smallest values from a list of integers, in "
            "ascending order. items may contain duplicates and may be empty; "
            "k may exceed len(items) (return all, sorted). Do not mutate "
            "items. Care about speed on large inputs.")

    def baseline_code(self) -> str | None:
        return "def solve(items, k):\n    return sorted(items)[:k]\n"

    def spec(self) -> SandboxSpec:
        return SandboxSpec(
            oracle_src=_ORACLE,
            workload_gen_src=_GEN,
            verdict_src=_VERDICT,
            criteria_cases=[
                {"name": "small", "args": [[5, 1, 4, 2, 3], 3]},
                {"name": "dups", "args": [[7, 7, 1, 1, 3], 2]},
                {"name": "empty", "args": [[], 4]},
                {"name": "k_over", "args": [[2, 1], 10]},
                {"name": "negatives", "args": [[-5, 3, -1, 0], 2]},
            ],
            workloads=[
                {"name": "uniform_2k", "n": 2000, "dist": "uniform",
                 "seed": 11, "k": 25},
                {"name": "dups_2k", "n": 2000, "dist": "duplicates",
                 "seed": 12, "k": 25},
                {"name": "skewed_2k", "n": 2000, "dist": "skewed",
                 "seed": 13, "k": 25},
            ],
            func_name="solve")


_DOMAINS: dict[str, type] = {"topk": TopKDomain}


def register_domain(name: str, domain_cls: type) -> None:
    _DOMAINS[name] = domain_cls


def get_domain(name: str):
    if name not in _DOMAINS:
        raise KeyError(f"unknown discovery domain '{name}' "
                       f"(known: {sorted(_DOMAINS)})")
    return _DOMAINS[name]()


def domain_names() -> list[str]:
    return sorted(_DOMAINS)
