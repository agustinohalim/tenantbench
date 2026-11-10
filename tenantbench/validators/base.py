"""Common interface for the validators compared in the paper (pre-registration §5)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Policy:
    """Which tables carry tenant data and what the tenant column is called."""

    tenant_tables: frozenset[str]
    tenant_column: str = "tenant_id"
    # Every table in the schema (tenant and shared), lowercased. Validators that keep a
    # table allowlist (V5, V6) use it; the others ignore it.
    known_tables: frozenset[str] = frozenset()


@dataclass
class Decision:
    accepted: bool
    sql: str  # SQL to execute: the input for rejecting validators, the rewrite for rewriters
    reasons: list[str] = field(default_factory=list)


class Validator:
    name = "base"
    rewrites = False

    def check(self, sql: str, policy: Policy, tenant: int) -> Decision:  # pragma: no cover
        raise NotImplementedError
