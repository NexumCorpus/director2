import itertools

def is_golomb(pos):
    diffs = set()
    for i in range(len(pos)):
        for j in range(i+1, len(pos)):
            d = pos[j] - pos[i]
            if d in diffs or d <= 0:
                return False
            diffs.add(d)
    return True

found = []
for comb in itertools.combinations(range(1, 18), 6):
    pos = sorted(comb)
    if pos[5] <= 17 and is_golomb(pos):
        found.append(pos)

print("Any with largest <=17:", found)
print("Count:", len(found))
