# Grok channel: gen-gsolo-G1
_session 019edd95-4884-7b23-ac82-3df125741e7b · 1 turns · model grok-build_


## Claude
In how many ways can 12 be written as an UNORDERED sum of positive integers each of which is at least 3? (e.g. 3+9 and 9+3 count once.)

Reason briefly, then end with exactly: ANSWER: <integer>

## Grok  _(grok-build, 43.0s)_
The problem requires counting the integer partitions of 12 (unordered sums) where every part is at least 3. These can be found by enumerating in non-increasing order:

- 1 part: 12  
- 2 parts: 9+3, 8+4, 7+5, 6+6  
- 3 parts: 6+3+3, 5+4+3, 4+4+4  
- 4 parts: 3+3+3+3  

No valid partitions exist with 5+ parts (minimum sum 15 exceeds 12) or any other combinations using only parts ≥3.

Total: 9.

ANSWER: 9
