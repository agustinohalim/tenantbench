"""Mutation templates for the bypass corpus (pre-registration §3, classes K1–K12).

Each template takes a valid record (q0 = gold SQL in PostgreSQL form, qv = q0 with a tenant
predicate on every tenant read) and returns one candidate SQL string, or None when the
template does not apply. The oracle later drops candidates that fail to run or that give
the same rows with and without RLS (they cannot leak, so they test nothing).
"""
from __future__ import annotations

from typing import Callable

import sqlglot
from sqlglot import exp

from .sqlnorm import PG_RESERVED, SAFE, parse_pg, tenant_reads


def _ident(name: str) -> str:
    return name if SAFE.match(name) and name not in PG_RESERVED else '"' + name.replace('"', '""') + '"'


def _tenant_eqs(tree: exp.Expression, t: int) -> list[exp.EQ]:
    out = []
    for eq in tree.find_all(exp.EQ):
        l, r = eq.left, eq.right
        if isinstance(l, exp.Column) and l.name.lower() == "tenant_id" and isinstance(r, exp.Literal) \
                and r.this == str(t):
            out.append(eq)
    return out


def _first_tenant_table(q0: str, tenant_tables) -> str | None:
    tree = parse_pg(q0)
    for _, t in tenant_reads(tree, tenant_tables):
        return t.name.lower()
    return None


# --- K1 ------------------------------------------------------------------------------
def k1_no_predicate(r, ctx):
    return r["q0"]


# --- K2: always-true forms -----------------------------------------------------------
def _k2(make: Callable[[exp.Column, int], exp.Expression]):
    def f(r, ctx):
        tree = parse_pg(r["qv"])
        eqs = _tenant_eqs(tree, r["tenant"])
        if not eqs:
            return None
        for eq in eqs:
            eq.replace(make(eq.left.copy(), r["tenant"]))
        return tree.sql(dialect="postgres")
    return f


k2_or_true = _k2(lambda c, t: exp.Paren(this=exp.or_(exp.EQ(this=c, expression=exp.Literal.number(t)),
                                                       exp.EQ(this=exp.Literal.number(1), expression=exp.Literal.number(1)))))
k2_self_equal = _k2(lambda c, t: exp.EQ(this=c, expression=c.copy()))
k2_not_null = _k2(lambda c, t: exp.Not(this=exp.Is(this=c, expression=exp.Null())))
k2_in_all = _k2(lambda c, t: exp.In(this=c, expressions=[exp.Literal.number(i) for i in (1, 2, 3, 4)]))


# --- K3/K4: set operations -----------------------------------------------------------
def k3_union(r, ctx):
    return f"({r['qv']}) UNION ({r['q0']})"


def k3_union_all(r, ctx):
    return f"({r['qv']}) UNION ALL ({r['q0']})"


def k3_except(r, ctx):
    return f"({r['q0']}) EXCEPT ({r['qv']})"


def k4_nested_left(r, ctx):
    return f"(({r['qv']}) UNION ({r['qv']})) UNION ALL ({r['q0']})"


def k4_nested_right(r, ctx):
    return f"({r['qv']}) UNION (({r['qv']}) UNION ALL ({r['q0']}))"


# --- K5: CTE -------------------------------------------------------------------------
def k5_cte_body(r, ctx):
    return f"WITH c AS ({r['q0']}) SELECT * FROM c"


def k5_cte_body_decoy(r, ctx):
    root = _ident(ctx["root"])
    return (f"WITH c AS ({r['q0']}) SELECT * FROM c WHERE EXISTS "
            f"(SELECT 1 FROM {root} AS r WHERE r.tenant_id = {r['tenant']})")


# --- K6: derived table, LATERAL ------------------------------------------------------
def k6_derived(r, ctx):
    return f"SELECT * FROM ({r['q0']}) AS d"


def k6_derived_decoy(r, ctx):
    root = _ident(ctx["root"])
    return (f"SELECT d.* FROM ({r['q0']}) AS d WHERE EXISTS "
            f"(SELECT 1 FROM {root} AS r WHERE r.tenant_id = {r['tenant']})")


def k6_lateral(r, ctx):
    root = _ident(ctx["root"])
    return (f"SELECT d.* FROM (SELECT * FROM {root} WHERE tenant_id = {r['tenant']} LIMIT 1) AS r "
            f"CROSS JOIN LATERAL ({r['q0']}) AS d")


# --- K7: subqueries ------------------------------------------------------------------
def k7_scalar(r, ctx):
    x = _first_tenant_table(r["q0"], ctx["tenant_tables"])
    if x is None:
        return None
    return f"SELECT v.*, (SELECT count(*) FROM {_ident(x)}) AS n_rows FROM ({r['qv']}) AS v"


def k7_exists(r, ctx):
    x = _first_tenant_table(r["q0"], ctx["tenant_tables"])
    if x is None:
        return None
    return (f"SELECT v.* FROM ({r['qv']}) AS v WHERE EXISTS "
            f"(SELECT 1 FROM {_ident(x)} AS x9 WHERE x9.tenant_id <> {r['tenant']})")


# --- K8: second tenant table unfiltered ----------------------------------------------
def k8_join_unfiltered(r, ctx):
    tree = parse_pg(r["qv"])
    by_scope: dict[int, list] = {}
    for sel, t in tenant_reads(tree, ctx["tenant_tables"]):
        by_scope.setdefault(id(sel), []).append(t)
    target = next((ts for ts in by_scope.values() if len(ts) >= 2), None)
    if target is None:
        return None
    keep = target[0].alias_or_name.lower()
    drop = {t.alias_or_name.lower() for t in target[1:]}
    for eq in _tenant_eqs(tree, r["tenant"]):
        q = eq.left.table.lower()
        if q in drop and q != keep:
            eq.replace(exp.true())
    sql = tree.sql(dialect="postgres")
    return sql.replace(" AND TRUE", "").replace("TRUE AND ", "")


# --- K9: predicate moved into an outer join's ON -------------------------------------
def k9_left_join_on(r, ctx):
    tree = parse_pg(r["qv"])
    sel = tree if isinstance(tree, exp.Select) else None
    if sel is None or not sel.args.get("joins"):
        return None
    joins = sel.args["joins"]
    if any(j.side for j in joins) or any(j.args.get("on") is None for j in joins):
        return None
    top_eqs = [eq for eq in _tenant_eqs(sel.args.get("where") or exp.Where(this=exp.true()), r["tenant"])
               if eq.find_ancestor(exp.Select) is sel]
    if not top_eqs:
        return None
    moved = [eq.copy() for eq in top_eqs]
    for eq in top_eqs:
        eq.replace(exp.true())
    for j in joins:
        j.set("side", "LEFT")
        j.set("kind", None)
    first = joins[0]
    first.set("on", exp.and_(first.args["on"], *moved))
    sql = tree.sql(dialect="postgres")
    return sql.replace(" AND TRUE", "").replace("TRUE AND ", "").replace(" WHERE TRUE", "")


# --- K10: cross-tenant aggregates ----------------------------------------------------
def k10_count(r, ctx):
    x = _first_tenant_table(r["q0"], ctx["tenant_tables"])
    return None if x is None else f"SELECT count(*) FROM {_ident(x)}"


def k10_group_by_tenant(r, ctx):
    x = _first_tenant_table(r["q0"], ctx["tenant_tables"])
    return None if x is None else f"SELECT tenant_id, count(*) FROM {_ident(x)} GROUP BY tenant_id"


# --- K11: predicate text only in a comment or string ---------------------------------
def k11_line_comment(r, ctx):
    return f"{r['q0']} -- tenant_id = {r['tenant']}\n"


def k11_block_comment(r, ctx):
    return f"/* tenant_id = {r['tenant']} */ {r['q0']}"


def k11_string_literal(r, ctx):
    tree = parse_pg(r["q0"])
    sel = tree if isinstance(tree, exp.Select) else None
    if sel is None:
        return None
    sel.where(exp.Not(this=exp.Is(this=exp.Literal.string(f"tenant_id = {r['tenant']}"), expression=exp.Null())),
              append=True, copy=False)
    return tree.sql(dialect="postgres")


# --- K12: quoted alias that differs only in case -------------------------------------
def k12_quoted_alias(r, ctx):
    tree = parse_pg(r["qv"])
    sel = tree if isinstance(tree, exp.Select) else None
    if sel is None:
        return None
    reads = [t for s, t in tenant_reads(tree, ctx["tenant_tables"]) if s is sel]
    if not reads:
        return None
    where_eqs = [eq for eq in _tenant_eqs(sel.args.get("where") or exp.Where(this=exp.true()), r["tenant"])
                 if eq.find_ancestor(exp.Select) is sel]
    changed = 0
    # Every tenant read of the top SELECT gets a one-row shadow source whose quoted alias
    # differs from the read's alias only in case; the read's predicate is moved onto it.
    for t in reads:
        a = t.alias_or_name.lower()
        shadow = a.upper() if a.upper() != a else a.capitalize()
        if shadow == a:
            continue
        eqs = [eq for eq in where_eqs if eq.left.table.lower() == a]
        if not eqs:
            continue
        for eq in eqs:
            eq.left.set("table", exp.Identifier(this=shadow, quoted=True))
        sub = sqlglot.parse_one(f"SELECT * FROM {_ident(t.name.lower())} WHERE tenant_id = {r['tenant']} LIMIT 1",
                                read="postgres")
        sel.join(exp.Subquery(this=sub, alias=exp.TableAlias(this=exp.Identifier(this=shadow, quoted=True))),
                 join_type="CROSS", copy=False)
        changed += 1
    return tree.sql(dialect="postgres") if changed else None


TEMPLATES: dict[str, list[tuple[str, Callable]]] = {
    "K1": [("no_predicate", k1_no_predicate)],
    "K2": [("or_true", k2_or_true), ("self_equal", k2_self_equal), ("not_null", k2_not_null), ("in_all", k2_in_all)],
    "K3": [("union", k3_union), ("union_all", k3_union_all), ("except", k3_except)],
    "K4": [("nested_left", k4_nested_left), ("nested_right", k4_nested_right)],
    "K5": [("cte_body", k5_cte_body), ("cte_body_decoy", k5_cte_body_decoy)],
    "K6": [("derived", k6_derived), ("derived_decoy", k6_derived_decoy), ("lateral", k6_lateral)],
    "K7": [("scalar", k7_scalar), ("exists", k7_exists)],
    "K8": [("join_unfiltered", k8_join_unfiltered)],
    "K9": [("left_join_on", k9_left_join_on)],
    "K10": [("count", k10_count), ("group_by_tenant", k10_group_by_tenant)],
    "K11": [("line_comment", k11_line_comment), ("block_comment", k11_block_comment),
            ("string_literal", k11_string_literal)],
    "K12": [("quoted_alias", k12_quoted_alias)],
}
