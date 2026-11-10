"""Run the corpus against every published release of the two practitioner validators.

  AskDB  @askdb/core: v7_askdb/versions/<ver>/ (npm, --ignore-scripts), adapter v7_askdb/guard.mjs
  sql-guardrail:      versions/sqlguard/<ver>/  (pip --no-deps --target), policy as in V6

Every corpus item leaks by construction (R_all != R_rls was checked when the corpus was
built), so for these rejecting validators "accepted" on a corpus item is a leak, and
"rejected" on a valid item is a false rejection. No oracle call is needed.

Usage: python -I scripts/version_sweep.py --split dev|test
Output: runs/<split>_versions.csv  (tool, version, released, cls, n, accepted)
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tenantbench.tenancy import LAYOUTS  # noqa: E402
from tenantbench.validators.v7_askdb import to_placeholder  # noqa: E402

ASKDB_RELEASED = {
    "0.5.0-beta.18": "2026-05-21", "1.0.0-beta.20": "2026-06-01", "1.0.0-beta.21": "2026-06-06",
    "1.0.0-beta.26": "2026-06-11", "1.0.0-beta.36": "2026-07-07", "1.0.0-beta.40": "2026-07-28",
    "1.0.0-beta.41": "2026-08-04", "1.0.0-beta.42": "2026-08-23", "1.0.0-beta.43": "2026-09-30",
    "1.0.0-beta.44": "2026-11-04", "1.0.0-beta.45": "2026-11-05", "1.0.0-beta.46": "2026-11-06",
    "1.0.0-beta.47": "2026-11-06", "1.0.0-beta.48": "2026-11-06", "1.0.0-beta.49": "2026-11-06",
    "1.0.0-beta.50": "2026-11-07", "1.0.0-beta.51": "2026-11-07", "1.0.0-beta.52": "2026-11-08",
    "1.0.0-beta.53": "2026-11-08", "1.0.0-beta.54": "2026-11-08", "1.0.0-beta.55": "2026-11-08",
    "1.0.0-rc.1": "2026-11-09",
}
H2A_VERSIONS = ("1.0.0-beta.42", "1.0.0-beta.43", "1.0.0-beta.52", "1.0.0-beta.53")
SQLGUARD_RELEASED = {"0.5.0": "2026-05-25", "0.5.1": "2026-06-07", "0.5.2": "2026-06-09"}

SQLGUARD_CHILD = r"""
import json, sys
sys.path.insert(0, sys.argv[1]); sys.path.insert(1, sys.argv[2])
import sqlguard
from tenantbench.validators.base import Policy
from tenantbench.validators.v6_sqlguardrail import build_policy
for line in sys.stdin:
    j = json.loads(line)
    p = Policy(frozenset(j["tenant_tables"]), known_tables=frozenset(j["known_tables"]))
    r = sqlguard.verify(j["sql"], build_policy(p), context={"tenant_id": j["tenant"]})
    print(json.dumps({"id": j["id"], "passed": bool(r.allowed), "v": sqlguard.__version__}))
"""


def items(split):
    work = ROOT / "data" / "work"
    rep = {r["db"]: r for r in json.loads((work / "load_report.json").read_text(encoding="utf-8"))}
    out = []
    for c in map(json.loads, (work / "corpus.jsonl").open(encoding="utf-8")):
        if c["split"] == split:
            out.append((c["cls"], c["db"], c["tenant"], c["sql"]))
    for v in map(json.loads, (work / "valid.jsonl").open(encoding="utf-8")):
        if v["status"] == "valid" and v["split"] == split:
            out.append(("valid", v["db"], v["tenant"], v["qv"]))
    return out, rep


def run_askdb(ver, its):
    lines = []
    for i, (_, db, t, sql) in enumerate(its):
        lay = LAYOUTS[db]
        lines.append(json.dumps({"id": i, "sql_placeholder": to_placeholder(sql, t), "tenant": t,
                                 "tenant_tables": [lay.root.table] + [c.table for c in lay.children]}))
    env = {**os.environ, "ASKDB_DIR": str(ROOT / "v7_askdb" / "versions" / ver / "node_modules" / "@askdb" / "core")}
    if ver == "1.0.0-beta.55":
        env["ASKDB_DIR"] = str(ROOT / "v7_askdb" / "node_modules" / "@askdb" / "core")
    p = subprocess.run(["node", "guard.mjs"], input="\n".join(lines) + "\n", capture_output=True, text=True,
                       encoding="utf-8", cwd=ROOT / "v7_askdb", env=env, check=True)
    res = {r["id"]: r["passed"] for r in map(json.loads, p.stdout.splitlines())}
    return [res[i] for i in range(len(its))]


def run_sqlguard(ver, its, rep):
    lines = [json.dumps({"id": i, "sql": sql, "tenant": t, "tenant_tables": rep[db]["tenant_tables"],
                         "known_tables": rep[db]["tenant_tables"] + rep[db]["shared_tables"]})
             for i, (_, db, t, sql) in enumerate(its)]
    p = subprocess.run([sys.executable, "-I", "-W", "ignore", "-c", SQLGUARD_CHILD,
                        str(ROOT / "versions" / "sqlguard" / ver), str(ROOT)],
                       input="\n".join(lines) + "\n", capture_output=True, text=True, encoding="utf-8", check=True)
    rows = list(map(json.loads, p.stdout.splitlines()))
    assert all(r["v"] == ver for r in rows), "wrong sql-guardrail version imported"
    res = {r["id"]: r["passed"] for r in rows}
    return [res[i] for i in range(len(its))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "test"], required=True)
    a = ap.parse_args()
    if a.split == "test" and not (ROOT / "results" / "PREREG_LOCK").exists():
        sys.exit("refusing: pre-registration not locked (results/PREREG_LOCK missing)")
    its, rep = items(a.split)
    rows = []
    paired = {}  # per-item decisions for the H2a contrasts
    jobs = [("askdb", v, d) for v, d in ASKDB_RELEASED.items()] + [("sql-guardrail", v, d) for v, d in SQLGUARD_RELEASED.items()]
    for tool, ver, date in jobs:
        acc = run_askdb(ver, its) if tool == "askdb" else run_sqlguard(ver, its, rep)
        if tool == "askdb" and ver in H2A_VERSIONS:
            paired[ver] = acc
        by = {}
        for (cls, *_), ok in zip(its, acc):
            n, k = by.get(cls, (0, 0))
            by[cls] = (n + 1, k + ok)
        for cls, (n, k) in by.items():
            rows.append({"tool": tool, "version": ver, "released": date, "cls": cls, "n": n, "accepted": k})
        tot = sum(v[0] for c, v in by.items() if c != "valid"), sum(v[1] for c, v in by.items() if c != "valid")
        fr = by.get("valid", (0, 0))
        print(f"{tool} {ver} ({date}): corpus leaks {tot[1]}/{tot[0]}, valid rejected {fr[0] - fr[1]}/{fr[0]}", flush=True)
    with (ROOT / "runs" / f"{a.split}_versions.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print()
    print("H2a, exact McNemar on corpus items (Holm over 2):")
    sys.path.insert(0, str(ROOT / "scripts"))
    from summarise import holm, mcnemar_exact
    corpus_idx = [i for i, it in enumerate(its) if it[0] != "valid"]
    ps, cnt = {}, {}
    for old, new in (("1.0.0-beta.42", "1.0.0-beta.43"), ("1.0.0-beta.52", "1.0.0-beta.53")):
        b = sum(1 for i in corpus_idx if paired[old][i] and not paired[new][i])
        c = sum(1 for i in corpus_idx if paired[new][i] and not paired[old][i])
        ps[f"{old} vs {new}"], cnt[f"{old} vs {new}"] = mcnemar_exact(b, c), (b, c)
    adj = holm(ps)
    for k in ps:
        print(f"  {k}: only old leaks {cnt[k][0]}, only new leaks {cnt[k][1]}, p={ps[k]:.3g}, Holm={adj[k]:.3g}")


if __name__ == "__main__":
    main()
