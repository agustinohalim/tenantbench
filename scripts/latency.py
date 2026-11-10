"""Validation latency per query (descriptive; pre-registration deviation P2).

Times validator.check() only, no oracle, on the test-split corpus and valid queries, on the same
machine as the main run. V1-V6: per-query wall time with time.perf_counter, 3 repetitions, the
median of the three kept per query; one warm-up pass first. V7 (AskDB) runs in Node through one
batch call, so only the amortised time (batch wall time / n, one Node start included) is reported.

Usage: python -I scripts/latency.py   Output: results/test/latency.md
"""
from __future__ import annotations

import json
import pathlib
import platform
import statistics
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from run_validators import policies, root_first  # noqa: E402

from tenantbench.validators.v1_regex import RegexValidator  # noqa: E402
from tenantbench.validators.v2_statement import StatementValidator  # noqa: E402
from tenantbench.validators.v3_scope import ScopeValidator  # noqa: E402
from tenantbench.validators.v4_rewrite import RewriteValidator  # noqa: E402
from tenantbench.validators.v5_reference import ReferenceValidator  # noqa: E402
from tenantbench.validators.v6_sqlguardrail import SqlGuardrailValidator  # noqa: E402
from tenantbench.validators.v7_askdb import AskDBValidator  # noqa: E402

REPS = 3


def main():
    pol = policies()
    work = ROOT / "data" / "work"
    items = [(c["sql"], c["db"], c["tenant"]) for c in map(json.loads, (work / "corpus.jsonl").open(encoding="utf-8"))
             if c["split"] == "test"]
    items += [(v["qv"], v["db"], v["tenant"]) for v in map(json.loads, (work / "valid.jsonl").open(encoding="utf-8"))
              if v["status"] == "valid" and v["split"] == "test"]
    lines = ["# Validation latency, test split (descriptive, deviation P2)", "",
             f"Items: {len(items)} (corpus + valid). Machine: {platform.processor() or platform.machine()}, "
             f"Python {platform.python_version()}. Median of {REPS} repetitions per query, one warm-up pass.", "",
             "| validator | median ms | p95 ms | max ms |", "|---|---|---|---|"]
    for v in [RegexValidator(), StatementValidator(), ScopeValidator(), RewriteValidator(),
              ReferenceValidator(), SqlGuardrailValidator()]:
        for sql, db, t in items:
            v.check(sql, pol[db], t)
        per = []
        for sql, db, t in items:
            reps = []
            for _ in range(REPS):
                t0 = time.perf_counter()
                v.check(sql, pol[db], t)
                reps.append((time.perf_counter() - t0) * 1000)
            per.append(statistics.median(reps))
        per.sort()
        p95 = per[int(0.95 * (len(per) - 1))]
        lines.append(f"| {v.name} | {statistics.median(per):.3f} | {p95:.3f} | {per[-1]:.3f} |")
        print(lines[-1], flush=True)
    v7 = AskDBValidator()
    t0 = time.perf_counter()
    v7.check_many([(s, pol[d], t) for s, d, t in items], [root_first(d) for _, d, _ in items])
    amort = (time.perf_counter() - t0) * 1000 / len(items)
    lines.append(f"| V7 | amortised {amort:.3f} (batch / n, Node start included) | — | — |")
    print(lines[-1])
    (ROOT / "results" / "test" / "latency.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
