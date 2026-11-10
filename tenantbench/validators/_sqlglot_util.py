"""Helpers shared by the sqlglot-based validators (V2, V3)."""
from __future__ import annotations

from sqlglot import exp


def conjuncts(cond: exp.Expression | None) -> list[exp.Expression]:
    """Split a condition on top-level AND only. Anything under OR/NOT stays one opaque term."""
    if cond is None:
        return []
    if isinstance(cond, exp.Where):
        return conjuncts(cond.this)
    if isinstance(cond, exp.Paren):
        return conjuncts(cond.this)
    if isinstance(cond, exp.And):
        return conjuncts(cond.left) + conjuncts(cond.right)
    return [cond]


def _is_tenant_value(e: exp.Expression, tenant: int) -> bool:
    if isinstance(e, exp.Literal) and not e.is_string:
        try:
            return int(e.this) == tenant
        except ValueError:
            return False
    return isinstance(e, (exp.Placeholder, exp.Parameter))


def tenant_qualifiers(cond: exp.Expression | None, column: str, tenant: int) -> set[str]:
    """Qualifiers (table alias, or '' when unqualified) carrying `column = tenant` as a conjunct."""
    found: set[str] = set()
    for c in conjuncts(cond):
        if not isinstance(c, exp.EQ):
            continue
        for col, val in ((c.left, c.right), (c.right, c.left)):
            if isinstance(col, exp.Column) and col.name.lower() == column.lower() and _is_tenant_value(val, tenant):
                found.add(col.table.lower())
    return found


def alias_of(t: exp.Table) -> str:
    return (t.alias_or_name or "").lower()
