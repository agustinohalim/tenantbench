# Validation latency, test split (descriptive, deviation P2)

Items: 2455 (corpus + valid). Machine: AMD64 Family 26 Model 36 Stepping 0, AuthenticAMD, Python 3.12.10. Median of 3 repetitions per query, one warm-up pass.

| validator | median ms | p95 ms | max ms |
|---|---|---|---|
| V1 | 0.022 | 0.039 | 0.141 |
| V2 | 0.910 | 2.455 | 7.293 |
| V3 | 1.099 | 2.787 | 7.874 |
| V4 | 2.494 | 6.513 | 16.517 |
| V5 | 2.047 | 5.123 | 16.832 |
| V6 | 3.966 | 10.302 | 33.259 |
| V7 | amortised 2.837 (batch / n, Node start included) | — | — |
