"""Turn BIRD gold SQL (SQLite) into PostgreSQL for the loaded schemas, and add tenant predicates.

Tables and columns were created lowercased (scripts/load_pg.py). SQLite matches identifiers
case-insensitively, quoted or not, so lowercasing every identifier keeps the gold meaning.
An identifier is quoted in the output only when PostgreSQL needs it (spaces, punctuation,
reserved words), which is also how a person or a model would usually write it.
"""
from __future__ import annotations

import re

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import traverse_scope

SAFE = re.compile(r"[a-z_][a-z0-9_]*\Z")
# PostgreSQL 17 reserved key words (Appendix C, "reserved" column), lowercased.
PG_RESERVED = frozenset("""
all analyse analyze and any array as asc asymmetric both case cast check collate column constraint
create current_catalog current_date current_role current_time current_timestamp current_user default
deferrable desc distinct do else end except false fetch for foreign from grant group having in
initially intersect into lateral leading limit localtime localtimestamp not null offset on only or
order placing primary references returning select session_user some symmetric system_user table then
to trailing true union unique user using variadic when where window with
""".split())


def _fix_identifiers(node: exp.Expression) -> exp.Expression:
    if isinstance(node, exp.Identifier):
        name = node.this.lower()
        return exp.Identifier(this=name, quoted=not SAFE.match(name) or name in PG_RESERVED)
    return node


def to_pg(sql_sqlite: str) -> str:
    tree = sqlglot.parse_one(sql_sqlite, read="sqlite")
    tree = tree.transform(_fix_identifiers)
    return tree.sql(dialect="postgres")


def parse_pg(sql: str) -> exp.Expression:
    return sqlglot.parse_one(sql, read="postgres")


def tenant_reads(tree: exp.Expression, tenant_tables: frozenset[str]):
    """Yield (select, table) for every direct read of a tenant table, scope by scope."""
    for sc in traverse_scope(tree):
        sel = sc.expression
        if not isinstance(sel, exp.Select):
            continue
        for t in sc.tables:
            if t.name.lower() in tenant_tables and t.name not in sc.cte_sources:
                yield sel, t


def _pred(table: exp.Table, tenant: int) -> exp.Expression:
    qual = table.alias_or_name.lower()
    ident = exp.Identifier(this=qual, quoted=not SAFE.match(qual) or qual in PG_RESERVED)
    return exp.EQ(this=exp.Column(this=exp.to_identifier("tenant_id"), table=ident),
                  expression=exp.Literal.number(tenant))


def _has_outer_join(sel: exp.Select) -> bool:
    return any(j.side for j in sel.args.get("joins") or [])


def add_tenant_predicates(sql_pg: str, tenant_tables: frozenset[str], tenant: int) -> str:
    """Scope every tenant-table read the way a careful author would, with the same rows as RLS.

    In a SELECT without outer joins the predicate goes into WHERE. Where an outer join is
    present, a WHERE predicate would also drop null-extended rows that RLS keeps, so each
    tenant table in that SELECT is replaced by `(SELECT * FROM t WHERE tenant_id = n) AS alias`.
    """
    tree = parse_pg(sql_pg)
    for sel, t in list(tenant_reads(tree, tenant_tables)):
        if _has_outer_join(sel):
            alias = t.alias_or_name
            inner = exp.select("*").from_(exp.Table(this=t.this.copy(), db=t.args.get("db"))).where(
                exp.EQ(this=exp.column("tenant_id"), expression=exp.Literal.number(tenant)))
            t.replace(exp.Subquery(this=inner, alias=exp.TableAlias(this=exp.to_identifier(alias))))
            continue
        sel.where(_pred(t, tenant), append=True, copy=False)
    return tree.sql(dialect="postgres")
