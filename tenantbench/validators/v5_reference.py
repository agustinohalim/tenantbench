"""V5: reference validator (pre-registration §5). Developed on the dev split only.

Starts from the per-scope rule of V3 and adds:
  * identifiers compared the way PostgreSQL resolves them: unquoted names fold to lower case,
    quoted names keep their case, so `"A".tenant_id` does not scope a read aliased `a`;
  * an allowlist: one SELECT statement (set operations allowed), no recursive CTE, no
    data-modifying CTE, every table known to the schema, no function outside a fixed list
    (functions that run SQL text or read server state would reach tables no scope shows);
  * an outer join's ON clause scopes the table it brings in only when that table is the
    join's nullable side (LEFT JOIN's right table, RIGHT JOIN's left table); it never
    scopes a preserved side, and FULL joins need the predicate inside a derived table;
  * an unqualified `tenant_id = t` scopes a read only when it is the only tenant read in
    that SELECT and no derived table or CTE in the same SELECT could also expose tenant_id.
Text inside string literals and comments never counts, because only the AST is read.
"""
from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import traverse_scope

from ._sqlglot_util import conjuncts
from .base import Decision, Policy, Validator

# Functions sqlglot parses into named expression classes are allowed (aggregates, string,
# date and math functions). Unknown functions (exp.Anonymous) must be in this list.
ALLOWED_ANONYMOUS = frozenset({
    "strftime", "julianday", "iif", "instr", "printf", "date_part", "to_char", "to_date",
    "to_timestamp", "age", "justify_days", "make_date", "split_part", "btrim", "initcap",
    "regexp_replace", "regexp_matches", "width_bucket", "percentile_cont", "string_agg",
})
DENIED_PREFIXES = ("pg_", "query_to_", "table_to_", "dblink", "lo_", "set_config", "current_setting",
                   "xpath", "cursor_to_", "database_to_", "schema_to_")


def _norm(ident: exp.Identifier | str | None) -> str:
    if ident is None:
        return ""
    if isinstance(ident, str):
        return ident.lower()
    return ident.this if ident.quoted else ident.this.lower()


def _table_key(t: exp.Table) -> str:
    return _norm(t.this if isinstance(t.this, exp.Identifier) else None) or t.name.lower()


def _alias_key(t: exp.Table) -> str:
    alias = t.args.get("alias")
    if alias is not None and alias.this is not None:
        return _norm(alias.this)
    return _table_key(t)


def _tenant_preds(cond, column: str, tenant: int) -> set[str]:
    """Normalised qualifiers with `<q>.tenant_id = <t>` as a top-level conjunct ('' = unqualified)."""
    out = set()
    for c in conjuncts(cond):
        if not isinstance(c, exp.EQ):
            continue
        for col, val in ((c.left, c.right), (c.right, c.left)):
            if not (isinstance(col, exp.Column) and _norm(col.this) == column):
                continue
            ok = (isinstance(val, exp.Literal) and not val.is_string and val.this.strip() == str(tenant)) \
                or isinstance(val, (exp.Placeholder, exp.Parameter))
            if ok:
                q = col.args.get("table")
                out.add(_norm(q) if q is not None else "")
    return out


class ReferenceValidator(Validator):
    name = "V5"

    def _allowlist(self, tree: exp.Expression, policy: Policy) -> list[str]:
        bad = []
        if not isinstance(tree, (exp.Select, exp.SetOperation)):
            bad.append("not a SELECT")
        for w in tree.find_all(exp.With):
            if w.args.get("recursive"):
                bad.append("recursive CTE")
        for node in tree.find_all(exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Command, exp.Into):
            bad.append(f"forbidden {type(node).__name__}")
        cte_names = {_norm(c.args["alias"].this) for c in tree.find_all(exp.CTE) if c.args.get("alias")}
        for t in tree.find_all(exp.Table):
            if not isinstance(t.this, exp.Identifier):
                bad.append("table expression that is not a plain name")
                continue
            k = _table_key(t)
            if k in cte_names and not t.args.get("db"):
                continue
            if k not in policy.known_tables and k not in policy.tenant_tables:
                bad.append(f"unknown table {t.sql()}")
        for f in tree.find_all(exp.Func):
            name = (f.name if isinstance(f, exp.Anonymous) else f.sql_name()).lower()
            if name.startswith(DENIED_PREFIXES):
                bad.append(f"denied function {name}")
            elif isinstance(f, exp.Anonymous) and name not in ALLOWED_ANONYMOUS:
                bad.append(f"unknown function {name}")
        return bad

    def check(self, sql: str, policy: Policy, tenant: int) -> Decision:
        col = policy.tenant_column.lower()
        try:
            stmts = sqlglot.parse(sql, read="postgres")
        except sqlglot.errors.ParseError as e:
            return Decision(False, sql, [f"parse error: {e}"])
        if len(stmts) != 1 or stmts[0] is None:
            return Decision(False, sql, ["not exactly one statement"])
        tree = stmts[0]
        reasons = self._allowlist(tree, policy)
        if reasons:
            return Decision(False, sql, reasons)
        try:
            scopes = traverse_scope(tree)
        except Exception as e:  # noqa: BLE001 - fail closed
            return Decision(False, sql, [f"scope error: {e}"])

        for sc in scopes:
            sel = sc.expression
            if not isinstance(sel, exp.Select):
                continue
            cte_here = {_norm(k) for k in sc.cte_sources}
            reads = [t for t in sc.tables
                     if _table_key(t) in policy.tenant_tables and not (_table_key(t) in cte_here and not t.args.get("db"))]
            if not reads:
                continue
            where_q = _tenant_preds(sel.args.get("where"), col, tenant)
            joins = sel.args.get("joins") or []
            has_full = any((j.side or "").upper() == "FULL" for j in joins)
            # Tables brought in by a join, and which join; FROM table has none.
            join_of = {id(j.this): j for j in joins if isinstance(j.this, exp.Table)}
            right_joined = [j for j in joins if (j.side or "").upper() == "RIGHT"]
            n_tenant_reads = len(reads)
            # Sources besides tenant tables that could also expose a tenant_id column. Shared
            # tables have none, so they do not make an unqualified predicate ambiguous.
            other_sources = len(sc.derived_table_scopes) + len(
                [x for x in sc.tables if _table_key(x) in cte_here and not x.args.get("db")])
            for t in reads:
                a = _alias_key(t)
                if has_full:
                    reasons.append(f"{a}: FULL JOIN in scope; filter inside a derived table instead")
                    continue
                j = join_of.get(id(t))
                ok = False
                if j is None or not j.side:  # FROM table or inner/cross join
                    ok = a in where_q
                    for jj in joins:
                        if not jj.side and jj.args.get("on") is not None and a in _tenant_preds(jj.args["on"], col, tenant):
                            ok = True
                    if j is None and right_joined:
                        # FROM table is the nullable side of a RIGHT JOIN: only ON of that join scopes it
                        ok = any(a in _tenant_preds(rj.args.get("on"), col, tenant) for rj in right_joined) or a in where_q
                elif j.side.upper() == "LEFT":
                    ok = a in where_q or a in _tenant_preds(j.args.get("on"), col, tenant)
                elif j.side.upper() == "RIGHT":
                    ok = a in where_q  # preserved side: ON does not filter it
                if not ok and "" in where_q and n_tenant_reads == 1 and other_sources == 0:
                    ok = True
                if not ok:
                    reasons.append(f"no tenant predicate for {t.sql()} in {sc.scope_type.name}")
        return Decision(not reasons, sql, reasons)
