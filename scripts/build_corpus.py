"""Build the bypass corpus from data/work/valid.jsonl (pre-registration §3).

Every template of every class is applied to every valid record. A candidate is kept only
if it runs under both roles and R_all != R_rls (it can leak). Per class and database at
most 50 candidates are kept, chosen in a fixed hash order, so no choice depends on any
validator. No validator is run here.

Output: data/work/corpus.jsonl and a count table on stdout (feeds Hasil_ValidatorTenant_1).
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
from tenantbench.mutate import TEMPLATES  # noqa: E402
from tenantbench.tenancy import LAYOUTS, schema_name  # noqa: E402

DEFAULT_CONN = "postgresql://postgres:tenantbench@127.0.0.1:55432/tenantbench"
CAP = 50


def order_key(*parts) -> str:
    return hashlib.sha256(("tenantbench-corpus:" + ":".join(map(str, parts))).encode()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--conn", default=DEFAULT_CONN)
    ap.add_argument("--cap", type=int, default=CAP)
    a = ap.parse_args()
    work = pathlib.Path(__file__).resolve().parents[1] / "data" / "work"
    valid = [json.loads(l) for l in (work / "valid.jsonl").open(encoding="utf-8")]
    valid = [v for v in valid if v["status"] == "valid"]

    cands = []
    for v in valid:
        lay = LAYOUTS[v["db"]]
        ctx = {"root": lay.root.table, "tenant_tables": lay.tenant_tables}
        for cls, temps in TEMPLATES.items():
            for name, fn in temps:
                try:
                    sql = fn(v, ctx)
                except Exception:  # noqa: BLE001 - template does not apply
                    sql = None
                if sql:
                    cands.append({**{k: v[k] for k in ("qid", "db", "tenant", "split")},
                                  "cls": cls, "template": name, "sql": sql})
    cands.sort(key=lambda c: order_key(c["db"], c["cls"], c["template"], c["qid"]))

    kept = collections.Counter()
    stats = collections.defaultdict(collections.Counter)
    seen = set()
    with (work / "corpus.jsonl").open("w", encoding="utf-8") as out:
        for c in cands:
            key = (c["db"], c["cls"])
            st = stats[key]
            st["generated"] += 1
            if kept[key] >= a.cap:
                st["over_cap"] += 1
                continue
            if (c["db"], c["sql"]) in seen:
                st["duplicate"] += 1
                continue
            seen.add((c["db"], c["sql"]))
            v = oracle.leaks(a.conn, c["sql"], c["sql"], c["tenant"], schema=schema_name(c["db"]))
            if v.leaks is None:
                st["error"] += 1
                continue
            if not v.leaks:
                st["same_rows"] += 1
                continue
            kept[key] += 1
            st["kept"] += 1
            c["cid"] = f"{c['db']}-{c['cls']}-{c['template']}-{c['qid']}"
            out.write(json.dumps(c) + "\n")
            out.flush()
    print("db,cls,generated,kept,error,same_rows,duplicate,over_cap")
    for (db, cls), st in sorted(stats.items(), key=lambda x: (x[0][0], int(x[0][1][1:]))):
        print(f"{db},{cls},{st['generated']},{st['kept']},{st['error']},{st['same_rows']},{st['duplicate']},{st['over_cap']}")


if __name__ == "__main__":
    main()
