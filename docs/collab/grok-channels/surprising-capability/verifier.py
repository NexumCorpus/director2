#!/usr/bin/env python3
"""Minimal verifier for the adversarial co-proving test.

Usage:
  python verifier.py P1 '2345'
  python verifier.py P2 '[1, 4, 6, 9, 11]'
  python verifier.py P3 '"XYZXYZX"'
  python verifier.py P4 '(2, 4, 3, 1)'
"""
import sys
import ast

PROBLEMS = {}

def register(pid):
    def deco(fn):
        PROBLEMS[pid] = fn
        return fn
    return deco

@register("P1")
def verify_p1(candidate):
    """Modular n. Accepts int or str that parses to int."""
    try:
        n = int(candidate) if not isinstance(candidate, int) else candidate
    except Exception:
        return False, f"Could not parse as int: {candidate!r}"
    if n <= 50:
        return False, "n must be > 50"
    ok = (n % 13 == 5 and
          (n + 3) % 17 == 2 and
          (n - 1) % 19 == 7 and
          n % 3 != 0)
    if ok:
        return True, f"Valid. n={n}"
    return False, f"Failed one or more congruences for n={n}"

@register("P2")
def verify_p2(candidate):
    """Set of exactly 5 distinct positives. Pairwise sums all unique. Returns (valid, info)."""
    try:
        if isinstance(candidate, str):
            s = ast.literal_eval(candidate)
        else:
            s = candidate
        s = sorted(set(int(x) for x in s))
    except Exception as e:
        return False, f"Parse error: {e}. Expected list/tuple of 5 ints e.g. [1,3,8,10,12]"
    if len(s) != 5:
        return False, f"Need exactly 5 distinct positives, got {len(s)}: {s}"
    if any(x < 1 for x in s):
        return False, "All must be positive integers >=1"
    # pairwise sums unique
    from itertools import combinations
    sums = [a + b for a, b in combinations(s, 2)]
    if len(sums) != len(set(sums)):
        dups = {}
        for sm in sums:
            dups[sm] = dups.get(sm, 0) + 1
        collisions = [sm for sm, c in dups.items() if c > 1]
        return False, f"Pairwise sums not unique. Collisions at sums: {collisions}"
    return True, f"Valid sidon-like set. max={max(s)}, set={s}"

@register("P3")
def verify_p3(candidate):
    """Constrained length-7 string."""
    try:
        if isinstance(candidate, str):
            s = ast.literal_eval(candidate) if candidate.strip().startswith(("'", '"', "[")) else candidate.strip().strip('"\'')
        else:
            s = str(candidate)
        s = str(s).strip()
    except Exception as e:
        return False, f"Parse error: {e}"
    if len(s) != 7:
        return False, f"Length must be 7, got {len(s)}"
    if s[0] != "X":
        return False, f"Must start with X, got {s[0]}"
    if s.count("Y") != 2:
        return False, f"Must contain exactly two Y, got {s.count('Y')}"
    for i in range(6):
        if s[i] == s[i+1]:
            return False, f"Adjacent identical letters at pos {i}: {s[i:i+2]}"
        if s[i:i+2] == "XZ":
            return False, f"Contains forbidden substring XZ at {i}"
    # alphabet check optional
    if not all(ch in "XYZ" for ch in s):
        return False, "Only X,Y,Z allowed"
    return True, f"Valid: {s}"

@register("P4")
def verify_p4(candidate):
    """4-tuple assignment."""
    try:
        if isinstance(candidate, str):
            t = ast.literal_eval(candidate)
        else:
            t = candidate
        t = tuple(int(x) for x in t)
    except Exception as e:
        return False, f"Parse error, expected 4-tuple: {e}"
    if len(t) != 4 or sorted(t) != [1,2,3,4]:
        return False, f"Must be permutation of 1-4, got {t}"
    a, b, c, d = t
    if not (a + b > c + d):
        return False, f"a+b > c+d failed: {a+b} > {c+d} ?"
    if not (a * c == b + d + 1):
        return False, f"a*c == b+d+1 failed: {a*c} == {b+d+1} ?"
    return True, f"Valid assignment: {t}"

def main():
    if len(sys.argv) < 3:
        print("Usage: python verifier.py <P1|P2|P3|P4> <candidate-literal>")
        print("Examples:")
        print('  python verifier.py P1 2345')
        print('  python verifier.py P2 "[1,2,4,7,11]"')
        print('  python verifier.py P3 \'"XYZXYZX"\'')
        print('  python verifier.py P4 "(2,4,3,1)"')
        sys.exit(1)
    pid = sys.argv[1].upper()
    cand_str = sys.argv[2]
    if pid not in PROBLEMS:
        print(f"Unknown problem {pid}. Known: {list(PROBLEMS)}")
        sys.exit(1)
    try:
        # Try literal first for safety, fall back to raw
        try:
            cand = ast.literal_eval(cand_str)
        except Exception:
            cand = cand_str
        valid, msg = PROBLEMS[pid](cand)
        status = "PASS" if valid else "FAIL"
        print(f"{pid} {status}: {msg}")
        sys.exit(0 if valid else 2)
    except Exception as e:
        print(f"Error verifying: {e}")
        sys.exit(3)

if __name__ == "__main__":
    main()
