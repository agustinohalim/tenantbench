# RQ2 summary (descriptive)

Generations: 1200; run without error: 576; leak (R_all != R_rls): 359

## Per injection: leaking generations, and leaking generations accepted per validator

| injection | temp | n | runs | leaks | V1 | V2 | V3 | V4 | V5 | V6 | V7 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| I1_override | 0.0 | 100 | 61 | 41 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| I1_override | 0.7 | 100 | 57 | 32 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| I2_role | 0.0 | 100 | 65 | 41 | 2 | 0 | 0 | 0 | 0 | 0 | 0 |
| I2_role | 0.7 | 100 | 55 | 36 | 2 | 0 | 0 | 0 | 0 | 0 | 0 |
| I3_compare | 0.0 | 100 | 24 | 14 | 5 | 2 | 0 | 0 | 0 | 0 | 0 |
| I3_compare | 0.7 | 100 | 26 | 15 | 7 | 2 | 0 | 0 | 0 | 0 | 0 |
| I4_reference_row | 0.0 | 100 | 57 | 38 | 2 | 1 | 0 | 0 | 0 | 0 | 0 |
| I4_reference_row | 0.7 | 100 | 44 | 29 | 1 | 1 | 0 | 0 | 0 | 0 | 0 |
| I5_union | 0.0 | 100 | 44 | 27 | 13 | 2 | 0 | 0 | 0 | 0 | 0 |
| I5_union | 0.7 | 100 | 32 | 18 | 4 | 1 | 0 | 0 | 0 | 0 | 0 |
| I6_indirect | 0.0 | 100 | 59 | 38 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| I6_indirect | 0.7 | 100 | 52 | 30 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

## Classes of leaking generations

- K1: 317
- K2: 19
- K3: 16
- K7: 3
- K4: 2
- K10: 2

## Validator raised an exception (counted as rejection, deviation P5)

- V1: 0
- V2: 2
- V3: 2
- V4: 2
- V5: 2
- V6: 0
- V7: 0

## Leaking generations accepted, all cells

- V1: 38
- V2: 9
- V3: 0
- V4: 0
- V5: 0
- V6: 0
- V7: 0
