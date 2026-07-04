# Grok channel: gen-gsolo-G3
_session 019edd9c-33eb-7ba2-a0ff-2a75f4acf51f · 1 turns · model grok-build_


## Claude
In how many ways can 15 be written as a sum of DISTINCT positive integers (order does not matter)?

Reason briefly, then end with exactly: ANSWER: <integer>

## Grok  _(grok-build, 61.9s)_
**This is the number of integer partitions of 15 into distinct positive parts (order irrelevant).**

By exhaustive enumeration (grouped by largest part, then decreasing distinct smaller parts):

- 1 part: 15  
- 2 parts: 14+1, 13+2, 12+3, 11+4, 10+5, 9+6, 8+7 (7)  
- 3 parts: 12+2+1, 11+3+1, 10+4+1, 10+3+2, 9+5+1, 9+4+2, 8+6+1, 8+5+2, 8+4+3, 7+6+2, 7+5+3, 6+5+4 (12)  
- 4 parts: 9+3+2+1, 8+4+2+1, 7+5+2+1, 7+4+3+1, 6+5+3+1, 6+4+3+2 (6)  
- 5 parts: 5+4+3+2+1 (1)  

No larger sets are possible (minimum sum of 6 distinct positives is 21). Total: 1+7+12+6+1 = 27.

This matches the known sequence and direct computation via recursion over strictly increasing parts.

ANSWER: 27
