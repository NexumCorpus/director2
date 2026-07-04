import itertools

def has_distinct_pair_sums(nums):
    sums = set()
    for a, b in itertools.combinations(nums, 2):
        sm = a + b
        if sm in sums:
            return False
        sums.add(sm)
    return True

def find_set_with_max_le(f):
    def bt(pos, current, used_sums):
        if len(current) == 6:
            return list(current)
        for x in range(pos, f + 1):
            new_sums = [x + y for y in current]
            if any(ns in used_sums for ns in new_sums):
                continue
            for ns in new_sums:
                used_sums.add(ns)
            current.append(x)
            res = bt(x + 1, current, used_sums)
            if res:
                return res
            current.pop()
            for ns in new_sums:
                used_sums.remove(ns)
        return None
    return bt(1, [], set())

def find_minimal_largest():
    for f in range(15, 60):
        res = find_set_with_max_le(f)
        if res:
            actual = max(res)
            return actual, res
    return None, None

min_max, the_set = find_minimal_largest()
print('Min max found:', min_max)
print('Set:', the_set)
if the_set:
    print('Verify:', has_distinct_pair_sums(the_set))
    sums = sorted(a + b for a, b in itertools.combinations(the_set, 2))
    print('Sums:', sums)
    print('Unique sums:', len(sums))
