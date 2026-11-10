"""V1: keyword check. If any tenant table name appears as a word, `tenant_id =` must appear
anywhere in the text; a query that names no tenant table is accepted."""
from __future__ import annotations

import re

from .base import Decision, Policy, Validator


class RegexValidator(Validator):
    name = "V1"

    def check(self, sql: str, policy: Policy, tenant: int) -> Decision:
        names = "|".join(re.escape(t) for t in sorted(policy.tenant_tables))
        if not re.search(rf"\b(?:{names})\b", sql, re.IGNORECASE):
            return Decision(True, sql, ["no tenant table named"])
        pat = re.compile(rf"\b{re.escape(policy.tenant_column)}\s*=", re.IGNORECASE)
        ok = bool(pat.search(sql))
        return Decision(ok, sql, [] if ok else ["no tenant predicate text"])
