import itertools

def has_distinct_pairwise_sums(nums):
    sums = set()
    for i in range(len(nums)):
        for j in range(i+1, len(nums)):
            s = nums[i] + nums[j]
            if s in sums:
                return False
            sums.add(s)
    return True

def find_min_max():
    # Search for smallest M where exists 6 distinct pos ints <=M with all pairwise sums distinct
    for M in range(10, 30):  # reasonable upper
        print(f"Checking M={M}")
        # Generate candidates: all increasing 6-tuples with max==M or <=M, but to optimize, fix largest =M and search smaller
        # But for small M, brute all combinations
        for comb in itertools.combinations(range(1, M+1), 6):
            if has_distinct_pairwise_sums(comb):
                return M, comb
        # Also check if any with max <M but we already would have found in previous
    return None, None

min_M, example = find_min_max()
print("Minimal M:", min_M)
print("Example set:", example)

# Also verify for M=13 if exists
print("\nChecking specifically for max<=13:")
found_13 = False
for comb in itertools.combinations(range(1,14),6):
    if max(comb)<=13 and has_distinct_pairwise_sums(comb):
        print("Found for 13:", comb)
        found_13 = True
        break
print("Exists for 13:", found_13)

# Check for M=12
print("\nChecking for max<=12:")
found_12 = False
for comb in itertools.combinations(range(1,13),6):
    if has_distinct_pairwise_sums(comb):
        print("Found for 12:", comb)
        found_12 = True
        break
print("Exists for 12:", found_12)
