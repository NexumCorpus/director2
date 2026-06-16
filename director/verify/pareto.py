"""Pareto / multi-objective utilities (trusted measurement code).

Pure-Python dominance, frontier extraction, and exact hypervolume for 1-3
objectives. Used by hook verifiers and discovery domains that grade
trade-off quality (e.g. ISR coverage vs redundancy vs cost) instead of a
single scalar — the hypervolume indicator rewards improving ANY objective
without imposing a weighting the operator never chose.

Conventions: a point is a sequence of objective values; ``senses`` is a
same-length sequence of ``"max"``/``"min"`` giving each objective's
direction. Internally everything is oriented to maximization.
"""

from __future__ import annotations


def _validate(points, senses) -> tuple:
    senses = tuple(senses)
    for s in senses:
        if s not in ("max", "min"):
            raise ValueError(f"sense must be 'max' or 'min', got {s!r}")
    for p in points:
        if len(p) != len(senses):
            raise ValueError(f"point {p!r} arity != {len(senses)} senses")
    return senses


def _orient(point, senses) -> tuple:
    return tuple(float(v) if s == "max" else -float(v)
                 for v, s in zip(point, senses))


def dominates(a, b, senses) -> bool:
    """True if ``a`` Pareto-dominates ``b``: no worse on every objective and
    strictly better on at least one."""
    senses = _validate((a, b), senses)
    na, nb = _orient(a, senses), _orient(b, senses)
    return (all(x >= y for x, y in zip(na, nb))
            and any(x > y for x, y in zip(na, nb)))


def pareto_frontier(points, senses) -> list[int]:
    """Indices of non-dominated points. Exact duplicates keep only the first
    occurrence, so the result is a minimal frontier."""
    pts = list(points)
    senses = _validate(pts, senses)
    normed = [_orient(p, senses) for p in pts]
    front: list[int] = []
    for i, p in enumerate(normed):
        keep = True
        for j, q in enumerate(normed):
            if j == i:
                continue
            never_worse = all(x >= y for x, y in zip(q, p))
            strictly_better = any(x > y for x, y in zip(q, p))
            # q dominates p, or q is an identical earlier duplicate
            if never_worse and (strictly_better or j < i):
                keep = False
                break
        if keep:
            front.append(i)
    return front


def hypervolume(points, ref, senses) -> float:
    """Exact hypervolume of the region dominated by ``points`` and bounded by
    ``ref``, for 1-3 objectives.

    ``ref`` must be a point every interesting solution strictly improves on
    (e.g. zero coverage, worst-case cost); points that fail to improve on it
    in every objective bound a degenerate box and are ignored.
    """
    pts_list = list(points)
    senses = _validate(pts_list + [ref], senses)
    r = _orient(ref, senses)
    pts = [_orient(p, senses) for p in pts_list]
    pts = [p for p in pts if all(v > b for v, b in zip(p, r))]
    if not pts:
        return 0.0
    dim = len(senses)
    if dim == 1:
        return max(p[0] for p in pts) - r[0]
    if dim == 2:
        return _hv2(pts, r)
    if dim == 3:
        # slice along the 3rd objective: each slab's volume is the 2D
        # hypervolume of every point above it times the slab height
        pts.sort(key=lambda p: p[2], reverse=True)
        hv = 0.0
        active: list[tuple[float, float]] = []
        for i, p in enumerate(pts):
            active.append((p[0], p[1]))
            z_lo = pts[i + 1][2] if i + 1 < len(pts) else r[2]
            if p[2] > z_lo:
                hv += _hv2(active, (r[0], r[1])) * (p[2] - z_lo)
        return hv
    raise ValueError("hypervolume supports 1-3 objectives")


def _hv2(pts, r) -> float:
    """2D hypervolume: sweep by first objective descending; each point adds
    the rectangle above the running best of the second objective."""
    hv, y_best = 0.0, r[1]
    for x, y in sorted(pts, key=lambda p: (-p[0], -p[1])):
        if y > y_best:
            hv += (x - r[0]) * (y - y_best)
            y_best = y
    return hv
