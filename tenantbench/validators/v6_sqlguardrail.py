"""V6: sql-guardrail 0.5.2 (MIT, github.com/nickusevich/sql-guardrail), used as published.

Policy: every known table is allowlisted; tenant tables carry
require_predicate tenant_id = ${tenant_id}; forbid.always_true_predicates stays on.
Rules that have nothing to do with tenancy (SELECT *, cartesian joins, LIMIT caps, join and
depth caps) are switched off, so a rejection here measures the tenant rule only. This is the
one configuration choice; the library code is not modified.
"""
from __future__ import annotations

import sqlguard
from sqlguard import ForbidPolicy, LimitsPolicy, RequiredPredicate, TablePolicy

from .base import Decision, Policy, Validator

PINNED = "0.5.2"


def build_policy(policy: Policy) -> sqlguard.Policy:
    tables = []
    for name in sorted(policy.known_tables | policy.tenant_tables):
        req = ()
        if name in policy.tenant_tables:
            req = (RequiredPredicate(column=policy.tenant_column, op="=", value="${tenant_id}"),)
        tables.append(TablePolicy(name=name, require_predicate=req))
    return sqlguard.Policy(
        read_only=True,
        tables=tuple(tables),
        forbid=ForbidPolicy(always_true_predicates=True, select_star=False, recursive_cte=False,
                            cartesian_join=False),
        limits=LimitsPolicy(max_joins=None, max_subquery_depth=None, max_limit_value=None,
                            max_offset_value=None, max_ast_nodes=None),
    )


class SqlGuardrailValidator(Validator):
    name = "V6"

    def __init__(self):
        assert sqlguard.__version__ == PINNED, sqlguard.__version__
        self._cache: dict[frozenset, sqlguard.Policy] = {}

    def check(self, sql: str, policy: Policy, tenant: int) -> Decision:
        key = policy.known_tables | policy.tenant_tables
        if key not in self._cache:
            self._cache[key] = build_policy(policy)
        res = sqlguard.verify(sql, self._cache[key], context={"tenant_id": tenant})
        return Decision(bool(res.allowed), sql, [str(v) for v in getattr(res, "violations", [])][:5])
