"""RQ4 run test (descriptive): does Cube Core keep a tenant filter on SQL API queries of each class?

Pre-registration §6 (option A) and deviation P3. Cube 1.8.21 in Docker, reading bird_financial through
a read-only BYPASSRLS role, so only Cube itself can filter. Two mechanisms:
  policy  - access_policy row_level filter tenant_id = { securityContext.tenant } (port 15432)
  rewrite - query_rewrite in the documented form: add the filter only if the claim exists (port 15433)
Three identities: t1 (tenant 1, group tenant), noclaim (group tenant, no tenant id), nogroup (empty).

A probe leaks when its result shows a tenant_id other than the session tenant, or a count or row
number above tenant 1's own count in PostgreSQL. For noclaim/nogroup any returned data row leaks.
Errors and empty results are recorded as such (closed). Output: results/rq4/cube_probe.{jsonl,md}
"""
from __future__ import annotations

import json
import pathlib

import psycopg

ROOT = pathlib.Path(__file__).resolve().parents[1]
PORTS = {"policy": 15432, "rewrite": 15433}
USERS = ["t1", "noclaim", "nogroup"]
OWN = {"loan": 192, "account": 1228}  # tenant 1 rows in PostgreSQL (incl. canary)

# (id, class, sql, kind) kind: tid = column 0 is tenant_id; cnt = column 0 is a count of loan rows;
# rows = row count compared with OWN["loan"]
PROBES = [
    ("P0", "base", "SELECT tenant_id, MEASURE(count) FROM loan GROUP BY 1", "tid"),
    ("P1", "K2", "SELECT tenant_id, MEASURE(count) FROM loan WHERE tenant_id = 1 OR tenant_id <> 1 GROUP BY 1", "tid"),
    ("P2", "K1", "SELECT tenant_id, MEASURE(count) FROM loan WHERE tenant_id = 2 GROUP BY 1", "tid"),
    ("P3", "K3", "SELECT tenant_id, MEASURE(count) FROM loan GROUP BY 1 UNION ALL "
                 "SELECT tenant_id, MEASURE(count) FROM account GROUP BY 1", "tid"),
    ("P4", "K4", "SELECT * FROM (SELECT tenant_id, MEASURE(count) c FROM loan GROUP BY 1 UNION ALL "
                 "SELECT * FROM (SELECT tenant_id, MEASURE(count) c FROM account GROUP BY 1 UNION ALL "
                 "SELECT tenant_id, MEASURE(count) c FROM trans GROUP BY 1) i) o", "tid"),
    ("P5", "K5", "WITH x AS (SELECT tenant_id, MEASURE(count) c FROM loan GROUP BY 1) SELECT * FROM x", "tid"),
    ("P6", "K6", "SELECT s.tenant_id, count(*) FROM (SELECT tenant_id, loan_id FROM loan) s GROUP BY 1", "tid"),
    ("P7", "K7", "SELECT tenant_id, loan_id FROM loan WHERE account_id IN (SELECT account_id FROM account)", "tid"),
    ("P8", "K8", "SELECT loan.tenant_id, account.tenant_id FROM loan CROSS JOIN account "
                 "WHERE loan.__cubeJoinField = account.__cubeJoinField", "tid2"),
    ("P9", "K9", "SELECT l.tenant_id, a.tenant_id FROM loan l LEFT JOIN account a ON l.account_id = a.account_id", "tid2"),
    ("P10", "K10", "SELECT MEASURE(count) FROM loan", "cnt"),
    ("P11", "K11", "SELECT tenant_id, MEASURE(count) FROM loan /* tenant_id = 1 */ GROUP BY 1", "tid"),
    ("P12", "K12", 'SELECT "L".tenant_id, count(*) FROM loan "L" GROUP BY 1', "tid"),
    ("P13", "raw", "SELECT count(*) FROM bird_financial.loan", "cnt"),
    ("P14", "meta", "SELECT tenant_id, count(*) FROM loan WHERE loan_id IN "
                    "(SELECT loan_id FROM loan WHERE tenant_id <> 1) GROUP BY 1", "tid"),
]


def judge(user, kind, rows):
    if not rows:
        return "empty"
    if user != "t1":
        return "leak"
    if kind == "tid":
        return "leak" if any(r[0] is not None and int(r[0]) != 1 for r in rows) else "ok"
    if kind == "tid2":
        return "leak" if any(x is not None and int(x) != 1 for r in rows for x in r[:2]) else "ok"
    if kind == "cnt":
        return "leak" if int(rows[0][0]) > OWN["loan"] else "ok"
    return "unknown"


def main():
    out_dir = ROOT / "results" / "rq4"
    out_dir.mkdir(parents=True, exist_ok=True)
    res = []
    for mech, port in PORTS.items():
        for user in USERS:
            for pid, cls, sql, kind in PROBES:
                row = {"mech": mech, "user": user, "probe": pid, "cls": cls, "sql": sql}
                try:
                    with psycopg.connect(host="127.0.0.1", port=port, user=user, password="rq4", dbname="db",
                                         autocommit=True, connect_timeout=10) as c:
                        rows = c.execute(sql).fetchall()
                    row["n_rows"] = len(rows)
                    row["tenants"] = sorted({int(x) for r in rows for x in (r[:2] if kind == "tid2" else r[:1])
                                             if x is not None}) if kind in ("tid", "tid2") else None
                    row["first"] = [str(x) for x in rows[0]] if rows else None
                    row["verdict"] = judge(user, kind, rows)
                except Exception as e:  # noqa: BLE001
                    row["verdict"] = "error"
                    row["error"] = str(e).splitlines()[0][:200]
                res.append(row)
                print(mech, user, pid, cls, row["verdict"], row.get("tenants") or row.get("first") or row.get("error", ""))
    (out_dir / "cube_probe.jsonl").write_text("".join(json.dumps(r) + "\n" for r in res), encoding="utf-8")
    lines = ["# Cube 1.8.21 run test (descriptive, RQ4, deviation P3)", "",
             "| probe | class | " + " | ".join(f"{m}/{u}" for m in PORTS for u in USERS) + " |",
             "|---|---|" + "---|" * (len(PORTS) * len(USERS))]
    for pid, cls, _, _ in PROBES:
        cells = [next(r["verdict"] for r in res if r["mech"] == m and r["user"] == u and r["probe"] == pid)
                 for m in PORTS for u in USERS]
        lines.append(f"| {pid} | {cls} | " + " | ".join(cells) + " |")
    (out_dir / "cube_probe.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
