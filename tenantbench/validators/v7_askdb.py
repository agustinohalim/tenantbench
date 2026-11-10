"""V7: AskDB tenant guardrail (@askdb/core 1.0.0-beta.55, Apache-2.0), through v7_askdb/guard.mjs.

AskDB expects the model to write a placeholder (`:tenant_tenant_ids`) where the tenant ID
goes, not a literal. The adapter rewrites `tenant_id = <t>` (any qualifier, either quoting)
to that placeholder before the check; every other literal stays, so `tenant_id = 4` or
`tenant_id IN (1, 2, 3, 4)` still reach AskDB as literals. The rule is fixed with the corpus.
Descriptive only: not part of the H2 McNemar contrasts.
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess

from .base import Decision, Policy, Validator

GUARD = pathlib.Path(__file__).resolve().parents[2] / "v7_askdb" / "guard.mjs"


def to_placeholder(sql: str, tenant: int) -> str:
    pat = re.compile(r'(\b|")tenant_id("?\s*=\s*)' + str(tenant) + r"(?![0-9.])", re.IGNORECASE)
    return pat.sub(lambda m: f"{m.group(1)}tenant_id{m.group(2)}{{PH}}", sql)


class AskDBValidator(Validator):
    name = "V7"

    def check_many(self, jobs: list[tuple[str, Policy, int]], root_first: list[list[str]]) -> list[Decision]:
        """Batch check. root_first[i] lists tenant tables with the root table first."""
        lines = [json.dumps({"id": i, "sql_placeholder": to_placeholder(sql, t), "tenant": t,
                             "tenant_tables": root_first[i]})
                 for i, (sql, _p, t) in enumerate(jobs)]
        proc = subprocess.run(["node", str(GUARD)], input="\n".join(lines) + "\n", capture_output=True,
                              text=True, encoding="utf-8", cwd=GUARD.parent, check=True)
        res = {r["id"]: r for r in map(json.loads, proc.stdout.splitlines())}
        return [Decision(res[i]["passed"], jobs[i][0], res[i]["codes"]) for i in range(len(jobs))]

    def check(self, sql: str, policy: Policy, tenant: int) -> Decision:
        tables = sorted(policy.tenant_tables)
        return self.check_many([(sql, policy, tenant)], [tables])[0]
