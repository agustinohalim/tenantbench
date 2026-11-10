"""Run every validator over the corpus and the valid set, and judge accepted queries with the oracle.

Usage: python -I scripts/run_validators.py --split dev|test [--conn URL]

--split test refuses to run unless results/PREREG_LOCK names the locked commit; the
pre-registration forbids test-split runs before the lock. V5 is developed on dev only.

Per (item, validator) one row in runs/<split>_runs.jsonl:
  kind     corpus | valid
  accepted validator decision
  leak     corpus: accepted and R_all(sql_run) != R_rls(sql, t); None when the run failed
  false_reject  valid: rejected, or a rewrite whose R_all != R_rls(qv, t)
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from tenantbench import oracle  # noqa: E402
from tenantbench.tenancy import LAYOUTS, schema_name  # noqa: E402
from tenantbench.validators.base import Policy  # noqa: E402
from tenantbench.validators.v1_regex import RegexValidator  # noqa: E402
from tenantbench.validators.v2_statement import StatementValidator  # noqa: E402
from tenantbench.validators.v3_scope import ScopeValidator  # noqa: E402
from tenantbench.validators.v4_rewrite import RewriteValidator  # noqa: E402
from tenantbench.validators.v5_reference import ReferenceValidator  # noqa: E402
from tenantbench.validators.v6_sqlguardrail import SqlGuardrailValidator  # noqa: E402
from tenantbench.validators.v7_askdb import AskDBValidator  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_CONN = "postgresql://postgres:tenantbench@127.0.0.1:55432/tenantbench"


def policies() -> dict[str, Policy]:
    rep = json.loads((ROOT / "data" / "work" / "load_report.json").read_text(encoding="utf-8"))
    out = {}
    for r in rep:
        out[r["db"]] = Policy(frozenset(r["tenant_tables"]), known_tables=frozenset(r["tenant_tables"] + r["shared_tables"]))
    return out


def root_first(db: str) -> list[str]:
    lay = LAYOUTS[db]
    return [lay.root.table] + [c.table for c in lay.children]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "test"], required=True)
    ap.add_argument("--conn", default=DEFAULT_CONN)
    a = ap.parse_args()
    if a.split == "test" and not (ROOT / "results" / "PREREG_LOCK").exists():
        sys.exit("refusing: pre-registration not locked (results/PREREG_LOCK missing)")

    pol = policies()
    work = ROOT / "data" / "work"
    items = []
    for c in map(json.loads, (work / "corpus.jsonl").open(encoding="utf-8")):
        if c["split"] == a.split:
            items.append({"kind": "corpus", "id": c["cid"], "cls": c["cls"], "template": c["template"],
                          "db": c["db"], "tenant": c["tenant"], "sql": c["sql"]})
    for v in map(json.loads, (work / "valid.jsonl").open(encoding="utf-8")):
        if v["status"] == "valid" and v["split"] == a.split:
            items.append({"kind": "valid", "id": f"{v['db']}-valid-{v['qid']}", "cls": "valid", "template": "",
                          "db": v["db"], "tenant": v["tenant"], "sql": v["qv"]})

    validators = [RegexValidator(), StatementValidator(), ScopeValidator(), RewriteValidator(),
                  ReferenceValidator(), SqlGuardrailValidator()]
    v7 = AskDBValidator().check_many([(i["sql"], pol[i["db"]], i["tenant"]) for i in items],
                                     [root_first(i["db"]) for i in items])

    out_path = ROOT / "runs" / f"{a.split}_runs.jsonl"
    out_path.parent.mkdir(exist_ok=True)
    with out_path.open("w", encoding="utf-8") as out:
        for k, it in enumerate(items):
            p, t, sch = pol[it["db"]], it["tenant"], schema_name(it["db"])
            decisions = [(v.name, v.rewrites, v.check(it["sql"], p, t)) for v in validators]
            decisions.append(("V7", False, v7[k]))
            for name, rewrites, d in decisions:
                row = {"id": it["id"], "kind": it["kind"], "cls": it["cls"], "template": it["template"],
                       "db": it["db"], "validator": name, "accepted": d.accepted, "reasons": d.reasons[:3]}
                if d.accepted:
                    verdict = oracle.leaks(a.conn, d.sql, it["sql"], t, schema=sch)
                    if it["kind"] == "corpus":
                        row["leak"] = verdict.leaks
                    else:
                        row["false_reject"] = None if verdict.leaks is None else bool(verdict.leaks)
                    if verdict.leaks is None:
                        row["error"] = verdict.detail
                else:
                    if it["kind"] == "corpus":
                        row["leak"] = False
                    else:
                        row["false_reject"] = True
                out.write(json.dumps(row) + "\n")
            out.flush()
    print(f"wrote {out_path} ({len(items)} items x {len(validators) + 1} validators)")


if __name__ == "__main__":
    main()
