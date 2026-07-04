# Grok channel: gen-gsolo-G2
_session 019edd99-1138-7142-ba32-8e8b139cfdbe · 1 turns · model grok-build_


## Claude
In how many ways can 10 be written as an ORDERED sum of positive integers each of which is at least 2? (e.g. 2+8 and 8+2 count separately.)

Reason briefly, then end with exactly: ANSWER: <integer>

## Grok  _(grok-build, 49.1s)_
This is the number of compositions (ordered partitions) of 10 with each part at least 2.

Let \(a_n\) be this number. It obeys the recurrence \(a_n = a_{n-1} + a_{n-2}\) (from the first part being 2 followed by such a composition of \(n-2\), or the first part being at least 3), with base cases \(a_2 = 1\) (just 2) and \(a_3 = 1\) (just 3).

This yields the sequence 1, 1, 2, 3, 5, 8, 13, 21, 34 for \(n = 2\) to \(n = 10\).

Equivalently, for \(k\) parts the count is \(\binom{10-k-1}{k-1}\) summed over feasible \(k = 1\) to 5, which totals \(1 + 7 + 15 + 10 + 1 = 34\).

ANSWER: 34
