"""V4: rewriter in the style of P2SQL §5.1.2 (Pedro et al., arXiv 2308.01990).

Instead of rejecting, every reference to a tenant table, in any scope, is replaced by
`(SELECT * FROM <table> WHERE tenant_id = <t>) AS <alias>`. The rewritten SQL is what runs;
the oracle compares R_all(rewrite(q)) with R_rls(q, t). It rejects only what it cannot parse.
Table names are matched the way sqlglot reports them, lowercased.
"""
from __future__ import annotations

import sqlglot
from sqlglot import exp

from .base import Decision, Policy, Validator


class RewriteValidator(Validator):
    name = "V4"
    rewrites = True

    def check(self, sql: str, policy: Policy, tenant: int) -> Decision:
        try:
            stmts = sqlglot.parse(sql, read="postgres")
        except sqlglot.errors.ParseError as e:
            return Decision(False, sql, [f"parse error: {e}"])
        if len(stmts) != 1 or stmts[0] is None:
            return Decision(False, sql, ["not exactly one statement"])
        tree = stmts[0]
        cte_names = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
        n = 0
        for t in list(tree.find_all(exp.Table)):
            name = t.name.lower()
            if name not in policy.tenant_tables or (name in cte_names and not t.args.get("db")):
                continue
            alias = t.alias_or_name
            inner = exp.select("*").from_(exp.Table(this=t.this.copy(), db=t.args.get("db"))).where(
                exp.EQ(this=exp.column(policy.tenant_column), expression=exp.Literal.number(tenant)))
            t.replace(exp.Subquery(this=inner, alias=exp.TableAlias(this=exp.to_identifier(alias))))
            n += 1
        return Decision(True, tree.sql(dialect="postgres"), [f"rewrote {n} reads"])
