"""V2: sqlglot, per statement.

Looks only at the outermost SELECT: every tenant table in its FROM/JOIN must carry an
equality tenant predicate as a top-level conjunct of WHERE (or of an INNER JOIN's ON).
Nested scopes (CTEs, derived tables, subqueries, set-operation branches past the first)
are not inspected. This is the design the paper expects to leak on classes K3–K7.
"""
from __future__ import annotations

import sqlglot
from sqlglot import exp

from ._sqlglot_util import alias_of, tenant_qualifiers
from .base import Decision, Policy, Validator


class StatementValidator(Validator):
    name = "V2"

    def check(self, sql: str, policy: Policy, tenant: int) -> Decision:
        try:
            stmts = sqlglot.parse(sql, read="postgres")
        except sqlglot.errors.ParseError as e:
            return Decision(False, sql, [f"parse error: {e}"])
        if len(stmts) != 1 or stmts[0] is None:
            return Decision(False, sql, ["not exactly one statement"])
        root = stmts[0]
        sel = root
        while isinstance(sel, exp.SetOperation):  # first branch only, as a per-statement check does
            sel = sel.left
        if not isinstance(sel, exp.Select):
            return Decision(False, sql, ["not a SELECT"])

        tables: list[exp.Table] = []
        frm = sel.args.get("from_") or sel.args.get("from")
        if frm is not None and isinstance(frm.this, exp.Table):
            tables.append(frm.this)
        inner_on: list[exp.Expression] = []
        for j in sel.args.get("joins") or []:
            if isinstance(j.this, exp.Table):
                tables.append(j.this)
            if not j.side and j.args.get("on") is not None:
                inner_on.append(j.args["on"])

        quals = tenant_qualifiers(sel.args.get("where"), policy.tenant_column, tenant)
        for on in inner_on:
            quals |= tenant_qualifiers(on, policy.tenant_column, tenant)

        reasons = []
        tenant_tabs = [t for t in tables if t.name.lower() in policy.tenant_tables]
        for t in tenant_tabs:
            a = alias_of(t)
            if a in quals or ("" in quals and len(tables) == 1):
                continue
            reasons.append(f"no tenant predicate for {t.name} as {a}")
        return Decision(not reasons, sql, reasons)
