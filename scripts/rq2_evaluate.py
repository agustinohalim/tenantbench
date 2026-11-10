"""RQ2 evaluation (descriptive): run validators and the oracle on the generated SQL.

For each generation: does it run, does it leak (R_all(q) != R_rls(q, t)), which validators accept
it, and, when it leaks, which class explains it (tenantbench.classify). V4 is judged on its
rewrite. Output: runs/rq2_eval.jsonl and runs/rq2_summary.md.
Committed before evaluation ran (pre-registration deviation P1).
"""
from __future__ import annotations

import collections
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from run_validators import policies, root_first  # noqa: E402

from tenantbench import oracle  # noqa: E402
from tenantbench.classify import classify  # noqa: E402
from tenantbench.tenancy import schema_name  # noqa: E402
from tenantbench.validators.v1_regex import RegexValidator  # noqa: E402
from tenantbench.validators.v2_statement import StatementValidator  # noqa: E402
from tenantbench.validators.v3_scope import ScopeValidator  # noqa: E402
from tenantbench.validators.v4_rewrite import RewriteValidator  # noqa: E402
from tenantbench.validators.v5_reference import ReferenceValidator  # noqa: E402
from tenantbench.validators.v6_sqlguardrail import SqlGuardrailValidator  # noqa: E402
from tenantbench.validators.v7_askdb import AskDBValidator  # noqa: E402

CONN = "postgresql://postgres:tenantbench@127.0.0.1:55432/tenantbench"
VS = ["V1", "V2", "V3", "V4", "V5", "V6", "V7"]


def main():
    gens = [json.loads(l) for l in (ROOT / "runs" / "rq2_generations.jsonl").open(encoding="utf-8")]
    pol = policies()
    vals = [RegexValidator(), StatementValidator(), ScopeValidator(), RewriteValidator(),
            ReferenceValidator(), SqlGuardrailValidator()]
    v7 = AskDBValidator().check_many([(g["sql"], pol[g["db"]], g["tenant"]) for g in gens],
                                     [root_first(g["db"]) for g in gens])
    rows = []
    with (ROOT / "runs" / "rq2_eval.jsonl").open("w", encoding="utf-8") as out:
        for k, g in enumerate(gens):
            p, t, sch = pol[g["db"]], g["tenant"], schema_name(g["db"])
            base = oracle.leaks(CONN, g["sql"], g["sql"], t, schema=sch)
            row = {k2: g[k2] for k2 in ("qid", "db", "tenant", "injection", "temperature")}
            row["runs"] = base.leaks is not None
            row["leaks"] = base.leaks
            row["cls"] = classify(g["sql"], p.tenant_tables, t) if base.leaks else None
            for v in vals:
                d = v.check(g["sql"], p, t)
                if not d.accepted:
                    row[v.name] = "rejected"
                elif v.rewrites:
                    r = oracle.leaks(CONN, d.sql, g["sql"], t, schema=sch)
                    row[v.name] = "error" if r.leaks is None else ("leak" if r.leaks else "ok")
                else:
                    row[v.name] = "error" if base.leaks is None else ("leak" if base.leaks else "ok")
            row["V7"] = "rejected" if not v7[k].accepted else ("error" if base.leaks is None else ("leak" if base.leaks else "ok"))
            out.write(json.dumps(row) + "\n")
            rows.append(row)

    lines = ["# RQ2 summary (descriptive)", ""]
    n = len(rows)
    lines.append(f"Generations: {n}; run without error: {sum(r['runs'] for r in rows)}; "
                 f"leak (R_all != R_rls): {sum(bool(r['leaks']) for r in rows)}")
    lines += ["", "## Per injection: leaking generations, and leaking generations accepted per validator", "",
              "| injection | temp | n | runs | leaks | " + " | ".join(VS) + " |",
              "|---|---|---|---|---|" + "---|" * len(VS)]
    grp = collections.defaultdict(list)
    for r in rows:
        grp[(r["injection"], r["temperature"])].append(r)
    for (inj, temp), rs in sorted(grp.items()):
        cells = [str(sum(1 for r in rs if r[v] == "leak")) for v in VS]
        lines.append(f"| {inj} | {temp} | {len(rs)} | {sum(r['runs'] for r in rs)} | "
                     f"{sum(bool(r['leaks']) for r in rs)} | " + " | ".join(cells) + " |")
    lines += ["", "## Classes of leaking generations", ""]
    for c, k in collections.Counter(r["cls"] for r in rows if r["leaks"]).most_common():
        lines.append(f"- {c}: {k}")
    lines += ["", "## Leaking generations accepted, all cells", ""]
    for v in VS:
        lines.append(f"- {v}: {sum(1 for r in rows if r[v] == 'leak')}")
    (ROOT / "runs" / "rq2_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
