"""Build the valid-query set (pre-registration §4) from BIRD dev gold SQL.

For each gold question of the five databases:
  * assign tenant t = 1 + (question_id mod 4) and split dev/test (20/80, by hash);
  * q0  = gold SQL in PostgreSQL form (sqlnorm.to_pg);
  * q_v = q0 with a tenant predicate on every tenant-table read (sqlnorm.add_tenant_predicates);
  * keep q_v as valid only if it runs and R_all(q_v) == R_rls(q_v, t);
  * record whether q0 itself leaks (R_all(q0) != R_rls(q0, t)): the K1 positive controls.
No validator is run here. Output: data/work/valid.jsonl plus a summary on stdout.

Usage: python -I scripts/build_valid.py <dev_20240627 dir> [--conn URL]
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from tenantbench import oracle  # noqa: E402
from tenantbench.sqlnorm import add_tenant_predicates, to_pg  # noqa: E402
from tenantbench.tenancy import LAYOUTS, N_TENANTS, schema_name  # noqa: E402

DEFAULT_CONN = "postgresql://postgres:tenantbench@127.0.0.1:55432/tenantbench"


def split_of(qid: int) -> str:
    h = int(hashlib.sha256(f"tenantbench-split:{qid}".encode()).hexdigest()[:8], 16)
    return "dev" if h % 5 == 0 else "test"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=pathlib.Path)
    ap.add_argument("--conn", default=DEFAULT_CONN)
    a = ap.parse_args()
    gold = json.loads((a.root / "dev.json").read_text(encoding="utf-8"))
    out_path = pathlib.Path(__file__).resolve().parents[1] / "data" / "work" / "valid.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    stats = collections.defaultdict(collections.Counter)
    with out_path.open("w", encoding="utf-8") as out:
        for g in gold:
            db = g["db_id"]
            if db not in LAYOUTS:
                continue
            qid = g["question_id"]
            t = 1 + qid % N_TENANTS
            sch = schema_name(db)
            rec = {"qid": qid, "db": db, "tenant": t, "split": split_of(qid), "question": g["question"]}
            st = stats[db]
            st["gold"] += 1
            try:
                q0 = to_pg(g["SQL"])
                qv = add_tenant_predicates(q0, LAYOUTS[db].tenant_tables, t)
            except Exception as e:  # noqa: BLE001 - recorded, never silently kept
                rec.update(status="transform_error", detail=str(e)[:200])
                st["transform_error"] += 1
                out.write(json.dumps(rec) + "\n")
                continue
            rec.update(q0=q0, qv=qv)
            v = oracle.leaks(a.conn, qv, qv, t, schema=sch)
            if v.leaks is None:
                rec.update(status="qv_error", detail=v.detail)
                st["qv_error"] += 1
            elif v.leaks:
                rec.update(status="qv_not_equal")
                st["qv_not_equal"] += 1
            else:
                rec.update(status="valid")
                st["valid"] += 1
                st[f"valid_{rec['split']}"] += 1
                g0 = oracle.leaks(a.conn, q0, q0, t, schema=sch)
                rec["q0_leaks"] = g0.leaks
                st["q0_leaks" if g0.leaks else ("q0_error" if g0.leaks is None else "q0_same")] += 1
            out.write(json.dumps(rec) + "\n")
            out.flush()
    for db, st in stats.items():
        print(db, dict(st))


if __name__ == "__main__":
    main()
