import itertools

def get_covered(queens, n=6):
    covered = set()
    for qr, qc in queens:
        # row
        for c in range(n):
            covered.add((qr, c))
        # col
        for r in range(n):
            covered.add((r, qc))
        # diag1: r - c == qr - qc
        diff = qr - qc
        for r in range(n):
            c = r - diff
            if 0 <= c < n:
                covered.add((r, c))
        # diag2: r + c == qr + qc
        summ = qr + qc
        for r in range(n):
            c = summ - r
            if 0 <= c < n:
                covered.add((r, c))
    return covered

positions = [(r, c) for r in range(6) for c in range(6)]

def find_min_queens():
    for k in range(1, 7):
        print(f"Checking k={k}...")
        for combo in itertools.combinations(positions, k):
            if len(get_covered(combo)) == 36:
                return k, combo
        print(f"No solution for k={k}")
    return None, None

k, solution = find_min_queens()
print("Minimum:", k)
print("Solution:", solution)
