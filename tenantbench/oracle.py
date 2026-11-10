"""Leak oracle: run a query with and without row-level security and compare results.

A query leaks for tenant t when its result as the unrestricted role differs from its
result as the tenant role under RLS (pre-registration §1). RLS is only the yardstick;
it is not one of the validators being compared.

Roles (created by scripts/load_pg.py):
  tb_all     BYPASSRLS, read-only on the benchmark schema
  tb_tenant  subject to RLS; policies read current_setting('tb.tenant')
"""
from __future__ import annotations

import decimal
import math
from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable

import psycopg
from psycopg import sql as pgsql

SIG_DIGITS = 9
TIMEOUT_MS = 20_000


def _norm(v: Any) -> Any:
    """Round numbers to 9 significant digits so float noise is not read as a leak."""
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, (int,)):
        return v
    if isinstance(v, (float, decimal.Decimal)):
        f = float(v)
        if math.isnan(f) or math.isinf(f) or f == 0.0:
            return f
        return float(f"{f:.{SIG_DIGITS}g}")
    return v


def as_multiset(rows: Iterable[tuple]) -> Counter:
    return Counter(tuple(_norm(v) for v in r) for r in rows)


@dataclass
class Outcome:
    ok: bool
    rows: Counter | None = None
    error: str | None = None


def run(conninfo: str, role: str, sql: str, tenant: int | None = None, schema: str | None = None) -> Outcome:
    """Run one read-only statement as `role`, in its own transaction that is always rolled back."""
    try:
        with psycopg.connect(conninfo, autocommit=False) as conn:
            with conn.cursor() as cur:
                cur.execute("SET TRANSACTION READ ONLY")
                cur.execute(f"SET LOCAL statement_timeout = {TIMEOUT_MS}")
                cur.execute(pgsql.SQL("SET LOCAL ROLE {}").format(pgsql.Identifier(role)))
                if schema is not None:
                    cur.execute("SELECT set_config('search_path', %s, true)", (schema,))
                if tenant is not None:
                    cur.execute("SELECT set_config('tb.tenant', %s, true)", (str(tenant),))
                cur.execute(sql)
                rows = cur.fetchall() if cur.description else []
            conn.rollback()
        return Outcome(True, as_multiset(rows))
    except psycopg.Error as e:  # syntax, runtime, timeout: counted apart, never as a leak
        return Outcome(False, error=f"{type(e).__name__}: {str(e).splitlines()[0]}")


@dataclass
class Verdict:
    leaks: bool | None  # None when either run failed
    detail: str


def leaks(conninfo: str, sql_run: str, sql_ref: str, tenant: int, schema: str | None = None) -> Verdict:
    """R_all(sql_run) != R_rls(sql_ref, t).

    For a rejecting validator sql_run == sql_ref == q. For a rewriting validator
    sql_run is rewrite(q) and sql_ref is the original q.
    """
    a = run(conninfo, "tb_all", sql_run, schema=schema)
    r = run(conninfo, "tb_tenant", sql_ref, tenant, schema=schema)
    if not a.ok or not r.ok:
        return Verdict(None, a.error or r.error or "error")
    return Verdict(a.rows != r.rows, "")
