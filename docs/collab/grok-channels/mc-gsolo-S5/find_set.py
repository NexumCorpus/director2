import itertools
import sys

def has_distinct_pairwise_sums(nums):
    sums = set()
    for i in range(len(nums)):
        for j in range(i+1, len(nums)):
            s = nums[i] + nums[j]
            if s in sums:
                return False
            sums.add(s)
    return True

def find_minimal_max(n=5, max_search=40):
    min_max = None
    best_set = None
    for M in range(n, max_search + 1):
        # Choose n-1 numbers from 1 to M-1, add M
        for combo in itertools.combinations(range(1, M), n-1):
            s = sorted(list(combo) + [M])
            if has_distinct_pairwise_sums(s):
                if min_max is None or M < min_max:
                    min_max = M
                    best_set = s
                    print(f"Found for M={M}: {s}")
                    return min_max, best_set  # since we go increasing M, first found is minimal
    return min_max, best_set

if __name__ == "__main__":
    mm, bs = find_minimal_max()
    print("Minimal largest:", mm)
    print("Set:", bs)
    # Verify
    if bs:
        print("Verification sums:", sorted([bs[i]+bs[j] for i in range(5) for j in range(i+1,5)]))
