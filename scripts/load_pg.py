"""Load the five BIRD dev databases into PostgreSQL with tenant_id columns and RLS.

Usage: python -I scripts/load_pg.py <dev_20240627 dir> [--conn URL] [--db NAME ...]

Per database:
  * schema bird_<db>; table and column names lowercased (SQLite matches them
    case-insensitively, so this keeps the gold SQL meaning the same);
  * column type: bigint / double precision when every non-null value fits, else text;
  * tenant tables get tenant_id (tenancy.LAYOUTS); child rows whose parent is missing
    are dropped and counted;
  * one canary row per tenant per tenant table;
  * RLS policy USING (tenant_id = current_setting('tb.tenant')::int) on tenant tables.
Writes a JSON load report next to the data (data/work/load_report.json).
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sqlite3
import sys

import psycopg
from psycopg import sql as S

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from tenantbench.tenancy import LAYOUTS, N_TENANTS, schema_name, tenant_of  # noqa: E402

DEFAULT_CONN = "postgresql://postgres:tenantbench@127.0.0.1:55432/tenantbench"


def col_type(values) -> str:
    kinds = {type(v) for v in values if v is not None}
    if kinds <= {int}:
        return "bigint"
    if kinds <= {int, float}:
        return "double precision"
    return "text"


def to_text(v):
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace")
    return v


def read_sqlite(path: pathlib.Path):
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    con.text_factory = lambda b: b.decode("utf-8", "replace")
    out = {}
    for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
        cols = [r[1].lower() for r in con.execute(f'PRAGMA table_info("{t}")')]
        rows = con.execute(f'SELECT * FROM "{t}"').fetchall()
        out[t.lower()] = (cols, rows)
    con.close()
    return out


def assign_tenants(layout, tables, report):
    """Return {table: list of tenant ids aligned with rows}; drops orphans in place."""
    ten: dict[str, list[int]] = {}
    key_maps: dict[tuple[str, str], dict] = {}

    def key_map(table, column):
        if (table, column) not in key_maps:
            cols, rows = tables[table]
            i = cols.index(column)
            key_maps[(table, column)] = {r[i]: ten[table][k] for k, r in enumerate(rows)}
        return key_maps[(table, column)]

    cols, rows = tables[layout.root.table]
    i = cols.index(layout.root.key)
    ten[layout.root.table] = [tenant_of(r[i]) for r in rows]
    for ch in layout.children:
        cols, rows = tables[ch.table]
        i = cols.index(ch.column)
        parent = key_map(ch.parent, ch.parent_column)
        # A direct child of the root that points at a root key missing from the root table
        # (toxicology: 101 molecule_ids used in atom/bond but absent from molecule) gets the
        # tenant its key would have had. Any other orphan is dropped.
        hash_missing = ch.parent == layout.root.table and ch.parent_column == layout.root.key
        kept, tids = [], []
        n_hashed = 0
        for r in rows:
            t = parent.get(r[i])
            if t is None and hash_missing and r[i] is not None:
                t = tenant_of(r[i])
                n_hashed += 1
            if t is None:
                continue
            kept.append(r)
            tids.append(t)
        report["orphans_dropped"][ch.table] = len(rows) - len(kept)
        report.setdefault("orphans_hashed", {})[ch.table] = n_hashed
        tables[ch.table] = (cols, kept)
        ten[ch.table] = tids
    return ten


def load_db(conn, root: pathlib.Path, db: str) -> dict:
    layout = LAYOUTS[db]
    sch = schema_name(db)
    tables = read_sqlite(root / "dev_databases" / db / f"{db}.sqlite")
    report = {"db": db, "orphans_dropped": {}, "rows": {}, "types": {}}
    ten = assign_tenants(layout, tables, report)

    with conn.cursor() as cur:
        cur.execute(S.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(S.Identifier(sch)))
        cur.execute(S.SQL("CREATE SCHEMA {}").format(S.Identifier(sch)))
        for t, (cols, rows) in tables.items():
            rows = [tuple(to_text(v) for v in r) for r in rows]
            types = [col_type(r[k] for r in rows) for k in range(len(cols))]
            # A column inferred numeric must not receive text from a canary later; canaries use NULL there.
            report["types"][t] = dict(zip(cols, types))
            is_tenant = t in ten
            defs = [S.SQL("{} {}").format(S.Identifier(c), S.SQL(ty)) for c, ty in zip(cols, types)]
            if is_tenant:
                defs.append(S.SQL("tenant_id integer NOT NULL"))
            cur.execute(S.SQL("CREATE TABLE {}.{} ({})").format(S.Identifier(sch), S.Identifier(t), S.SQL(", ").join(defs)))
            all_cols = cols + (["tenant_id"] if is_tenant else [])
            copy = S.SQL("COPY {}.{} ({}) FROM STDIN").format(
                S.Identifier(sch), S.Identifier(t), S.SQL(", ").join(map(S.Identifier, all_cols)))
            with cur.copy(copy) as cp:
                for k, r in enumerate(rows):
                    cp.write_row(r + ((ten[t][k],) if is_tenant else ()))
                if is_tenant:
                    for tid in range(1, N_TENANTS + 1):
                        canary = tuple(f"canary-{tid}" if ty == "text" else None for ty in types)
                        cp.write_row(canary + (tid,))
            report["rows"][t] = len(rows)
            if is_tenant:
                cur.execute(S.SQL("CREATE INDEX ON {}.{} (tenant_id)").format(S.Identifier(sch), S.Identifier(t)))
                cur.execute(S.SQL("ALTER TABLE {}.{} ENABLE ROW LEVEL SECURITY").format(S.Identifier(sch), S.Identifier(t)))
                cur.execute(S.SQL("CREATE POLICY tenant_rows ON {}.{} USING (tenant_id = current_setting('tb.tenant')::int)")
                            .format(S.Identifier(sch), S.Identifier(t)))
        for ch in layout.children:
            cur.execute(S.SQL("CREATE INDEX ON {}.{} ({})").format(S.Identifier(sch), S.Identifier(ch.table), S.Identifier(ch.column)))
        cur.execute(S.SQL("GRANT USAGE ON SCHEMA {} TO tb_all, tb_tenant").format(S.Identifier(sch)))
        cur.execute(S.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA {} TO tb_all, tb_tenant").format(S.Identifier(sch)))
        cur.execute(S.SQL("ANALYZE"))
    report["tenant_tables"] = sorted(layout.tenant_tables)
    report["shared_tables"] = sorted(set(tables) - layout.tenant_tables)
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=pathlib.Path)
    ap.add_argument("--conn", default=DEFAULT_CONN)
    ap.add_argument("--db", nargs="*", default=list(LAYOUTS))
    a = ap.parse_args()
    with psycopg.connect(a.conn, autocommit=True) as conn:
        conn.execute("""DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='tb_all') THEN CREATE ROLE tb_all BYPASSRLS; END IF;
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='tb_tenant') THEN CREATE ROLE tb_tenant; END IF;
        END $$""")
        reports = []
        for db in a.db:
            r = load_db(conn, a.root, db)
            print(db, {k: v for k, v in r["rows"].items()}, "orphans:", r["orphans_dropped"], flush=True)
            reports.append(r)
    out = pathlib.Path(__file__).resolve().parents[1] / "data" / "work" / "load_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(reports, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
