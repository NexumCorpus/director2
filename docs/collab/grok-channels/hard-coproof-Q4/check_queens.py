positions = [(1,6), (3,2), (5,4)]
queens = set(positions)

def is_attacked(r, c, queens):
    if (r, c) in queens:
        return True
    for qr, qc in queens:
        if r == qr or c == qc or abs(r - qr) == abs(c - qc):
            if r == qr:
                dr, dc = 0, 1 if c > qc else -1
            elif c == qc:
                dr, dc = 1 if r > qr else -1, 0
            else:
                dr = 1 if r > qr else -1
                dc = 1 if c > qc else -1
            cr, cc = qr + dr, qc + dc
            blocked = False
            while (cr, cc) != (r, c):
                if (cr, cc) in queens:
                    blocked = True
                    break
                cr += dr
                cc += dc
            if not blocked:
                return True
    return False

all_covered = True
uncovered = []
for r in range(1, 7):
    for c in range(1, 7):
        if not is_attacked(r, c, queens):
            all_covered = False
            uncovered.append((r, c))
print('All covered:', all_covered)
print('Uncovered:', uncovered)
print('Number of queens:', len(queens))
