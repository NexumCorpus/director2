# Grok channel: gen-gsolo-G4
_session 019edda0-75a8-7ab1-861b-dbe255aca831 · 1 turns · model grok-build_


## Claude
In how many ways can 9 be written as an ORDERED sum of exactly 4 positive integers?

Reason briefly, then end with exactly: ANSWER: <integer>

## Grok  _(grok-build, 41.8s)_
The problem asks for the number of compositions of 9 into exactly 4 positive parts (ordered 4-tuples of integers \(\geq 1\) that sum to 9).

This is equivalent to the number of non-negative integer solutions to \(y_1 + y_2 + y_3 + y_4 = 5\) after the substitution \(x_i = y_i + 1\).

By the stars-and-bars theorem, the count is \(\binom{5 + 4 - 1}{4 - 1} = \binom{8}{3} = 56\).

(Equivalently, the closed-form formula for the number of compositions of \(n\) into exactly \(k\) positive parts is \(\binom{n-1}{k-1}\), which gives \(\binom{8}{3} = 56\).)

This matches exhaustive enumeration via code.

ANSWER: 56
