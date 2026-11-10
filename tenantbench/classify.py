"""Assign an LLM-generated query to the structural class that explains its leak (RQ2, descriptive).

Rules fixed at commit time, before RQ2 results were seen (pre-registration deviation P1).
Applied only to queries that leak (R_all != R_rls). The first matching rule wins:

  K11  `tenant_id = <t>` appears in the text but no AST equality predicate on tenant_id exists
  K1   tenant_id appears in no WHERE, HAVING or JOIN condition
  K2   a tenant_id predicate that is not `col = <literal>` (OR beside it, IN, IS NOT NULL, col = col, <>)
  K3/4 a set operation with a branch that reads a tenant table without a tenant predicate
       (K4 when set operations nest)
  K5   a CTE body reads a tenant table without a tenant predicate
  K6   a derived table (or LATERAL) reads a tenant table without a tenant predicate
  K7   a subquery in WHERE/SELECT/HAVING reads a tenant table without a tenant predicate
  K10  the outermost SELECT aggregates and reads a tenant table without a tenant predicate
  K9   a tenant predicate sits only in the ON clause of an outer join
  K8   some tenant read in a SELECT has a predicate and another read in the same SELECT has none
  K12  a quoted alias whose lowercase form equals another alias in the query
  other  none of the above (e.g. wrong tenant literal)
"""
from __future__ import annotations

import re

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import ScopeType, traverse_scope


def _eq_preds(sel: exp.Select, t: int) -> set[str]:
    out = set()
    w = sel.args.get("where")
    nodes = list(w.find_all(exp.EQ)) if w is not None else []
    for j in sel.args.get("joins") or []:
        if not j.side and j.args.get("on") is not None:
            nodes += list(j.args["on"].find_all(exp.EQ))
    for eq in nodes:
        for col, val in ((eq.left, eq.right), (eq.right, eq.left)):
            if isinstance(col, exp.Column) and col.name.lower() == "tenant_id" and isinstance(val, exp.Literal) \
                    and val.this == str(t) and eq.find_ancestor(exp.Select) is sel:
                out.add(col.table.lower())
    return out


def classify(sql: str, tenant_tables: frozenset[str], t: int) -> str:
    try:
        tree = sqlglot.parse_one(sql, read="postgres")
    except Exception:  # noqa: BLE001
        return "unparsed"
    cols = [c for c in tree.find_all(exp.Column) if c.name.lower() == "tenant_id"]
    eq_any = any(isinstance(c.parent, exp.EQ) and any(isinstance(x, exp.Literal) and x.this == str(t)
                 for x in (c.parent.left, c.parent.right)) for c in cols)
    if not eq_any and re.search(rf"tenant_id\s*=\s*{t}\b", sql, re.I):
        return "K11"
    pred_cols = [c for c in cols if c.find_ancestor(exp.Where, exp.Having, exp.Join) is not None]
    if not pred_cols:
        return "K1"
    for c in cols:
        p = c.parent
        if isinstance(p, (exp.In, exp.NEQ, exp.Is)) or (isinstance(p, exp.EQ) and isinstance(p.left, exp.Column)
                                                         and isinstance(p.right, exp.Column)):
            return "K2"
        if isinstance(p, exp.EQ) and isinstance(p.parent, exp.Or):
            return "K2"
    try:
        scopes = traverse_scope(tree)
    except Exception:  # noqa: BLE001
        return "unparsed"
    unfiltered: list = []
    partly: bool = False
    for sc in scopes:
        sel = sc.expression
        if not isinstance(sel, exp.Select):
            continue
        reads = [x for x in sc.tables if x.name.lower() in tenant_tables and x.name not in sc.cte_sources]
        if not reads:
            continue
        q = _eq_preds(sel, t)
        miss = [x for x in reads if x.alias_or_name.lower() not in q and not ("" in q and len(reads) == 1)]
        if miss:
            unfiltered.append(sc)
            if len(miss) < len(reads):
                partly = True
    nested_setops = any(isinstance(s.parent, exp.SetOperation) or any(isinstance(x, exp.SetOperation) for x in [s.left, s.right])
                        for s in tree.find_all(exp.SetOperation))
    for sc in unfiltered:
        if sc.scope_type == ScopeType.SET_OPERATION or isinstance(sc.expression.parent, exp.SetOperation):
            return "K4" if nested_setops else "K3"
    for sc in unfiltered:
        if sc.scope_type == ScopeType.CTE:
            return "K5"
    for sc in unfiltered:
        if sc.scope_type == ScopeType.DERIVED_TABLE:
            return "K6"
    for sc in unfiltered:
        if sc.scope_type in (ScopeType.SUBQUERY, ScopeType.UDTF):
            return "K7"
    root_unf = [sc for sc in unfiltered if sc.scope_type == ScopeType.ROOT]
    if root_unf and root_unf[0].expression.find(exp.AggFunc) is not None and not partly:
        return "K10"
    for j in tree.find_all(exp.Join):
        if j.side and j.args.get("on") is not None and any(c.name.lower() == "tenant_id"
                                                           for c in j.args["on"].find_all(exp.Column)):
            return "K9"
    if partly:
        return "K8"
    aliases = [a.this for a in tree.find_all(exp.TableAlias) if isinstance(a.this, exp.Identifier)]
    quoted = {i.this.lower() for i in aliases if i.quoted and i.this != i.this.lower()}
    plain = {i.this.lower() for i in aliases if not i.quoted}
    if quoted & plain:
        return "K12"
    return "other"
