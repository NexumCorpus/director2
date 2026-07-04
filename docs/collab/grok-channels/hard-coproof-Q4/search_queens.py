
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

def covers_all(queens):
    for r in range(1, 7):
        for c in range(1, 7):
            if not is_attacked(r, c, queens):
                return False
    return True

# Check for 1 queen first
found_one = False
for r1 in range(1,7):
    for c1 in range(1,7):
        if covers_all([(r1,c1)]):
            found_one = True
            print('1 queen works at', (r1,c1))
            break
    if found_one: break
print('Any 1-queen:', found_one)

# Brute for 2 queens
found_two = False
solutions = []
for r1 in range(1,7):
    for c1 in range(1,7):
        for r2 in range(r1,7):
            for c2 in range(1,7):
                if r1 == r2 and c1 >= c2: continue  # avoid duplicates and same
                pos = [(r1,c1), (r2,c2)]
                if covers_all(pos):
                    found_two = True
                    solutions.append(pos)
                    break
            if found_two and len(solutions)>0: break
        if found_two and len(solutions)>0: break
    if found_two and len(solutions)>0: break
print('Any 2-queen:', found_two)
print('Example solutions:', solutions[:3] if solutions else None)
