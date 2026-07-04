import itertools

def is_golomb(pos):
    diffs = set()
    for i in range(len(pos)):
        for j in range(i+1, len(pos)):
            d = pos[j] - pos[i]
            if d in diffs or d == 0:
                return False
            diffs.add(d)
    return True

# Find minimal max for 6 distinct positive integers
min_max = float('inf')
best = None
for max_val in range(6, 40):  # start from small
    candidates = range(1, max_val+1)
    for comb in itertools.combinations(candidates, 6):
        pos = sorted(comb)
        if pos[-1] > min_max:
            break  # no need larger
        if is_golomb(pos):
            if pos[-1] < min_max:
                min_max = pos[-1]
                best = pos
                print("Found", best, "max", min_max)
                # continue to ensure minimal
    if min_max < max_val:  # if found smaller, can stop early but check up to current
        pass

print("Minimal largest:", min_max)
print("One such set:", best)
