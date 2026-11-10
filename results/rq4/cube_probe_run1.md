# Cube 1.8.21 run test (descriptive, RQ4, deviation P3)

| probe | class | policy/t1 | policy/noclaim | policy/nogroup | rewrite/t1 | rewrite/noclaim | rewrite/nogroup |
|---|---|---|---|---|---|---|---|
| P0 | base | ok | error | error | ok | leak | leak |
| P1 | K2 | ok | error | error | ok | leak | leak |
| P2 | K1 | empty | error | error | empty | leak | leak |
| P3 | K3 | ok | error | error | ok | leak | leak |
| P4 | K4 | ok | error | error | ok | leak | leak |
| P5 | K5 | ok | error | error | ok | leak | leak |
| P6 | K6 | ok | error | error | ok | leak | leak |
| P7 | K7 | ok | error | error | error | leak | leak |
| P8 | K8 | ok | error | error | ok | leak | leak |
| P9 | K9 | error | error | error | error | error | error |
| P10 | K10 | ok | error | error | ok | leak | leak |
| P11 | K11 | ok | error | error | ok | leak | leak |
| P12 | K12 | ok | error | error | ok | leak | leak |
| P13 | raw | error | error | error | error | error | error |
| P14 | meta | empty | error | error | error | leak | leak |
