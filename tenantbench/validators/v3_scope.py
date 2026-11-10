"""V3: sqlglot, per SELECT scope.

Every SELECT scope that reads a tenant table directly must carry an equality tenant
predicate for that read as a top-level conjunct of its WHERE (or an INNER JOIN's ON).
Scopes are taken from sqlglot's optimizer (CTEs, derived tables, subqueries, set-operation
branches). Unlike V5 it does not follow tenant data through CTE or derived-table outputs,
does not whitelist constructs, and trusts any conjunct regardless of its position.
"""
from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import traverse_scope

from ._sqlglot_util import alias_of, tenant_qualifiers
from .base import Decision, Policy, Validator


class ScopeValidator(Validator):
    name = "V3"

    def check(self, sql: str, policy: Policy, tenant: int) -> Decision:
        try:
            stmts = sqlglot.parse(sql, read="postgres")
        except sqlglot.errors.ParseError as e:
            return Decision(False, sql, [f"parse error: {e}"])
        if len(stmts) != 1 or stmts[0] is None:
            return Decision(False, sql, ["not exactly one statement"])
        root = stmts[0]
        if not isinstance(root, (exp.Select, exp.SetOperation)):
            return Decision(False, sql, ["not a SELECT"])

        try:
            scopes = traverse_scope(root)
        except Exception as e:  # sqlglot raises plain errors on odd shapes; fail closed
            return Decision(False, sql, [f"scope error: {e}"])

        reasons = []
        for sc in scopes:
            sel = sc.expression
            if not isinstance(sel, exp.Select):
                continue
            reads = [t for t in sc.tables if t.name.lower() in policy.tenant_tables and t.name not in sc.cte_sources]
            if not reads:
                continue
            quals = tenant_qualifiers(sel.args.get("where"), policy.tenant_column, tenant)
            for j in sel.args.get("joins") or []:
                if not j.side and j.args.get("on") is not None:
                    quals |= tenant_qualifiers(j.args["on"], policy.tenant_column, tenant)
            n_sources = len(sc.tables) + len(sc.derived_tables)
            for t in reads:
                a = alias_of(t)
                if a in quals or ("" in quals and n_sources == 1):
                    continue
                reasons.append(f"no tenant predicate for {t.name} as {a} in {sc.scope_type.name}")
        return Decision(not reasons, sql, reasons)
