"""Hand-written cases on a toy schema. Not the benchmark corpus; these only pin behaviour."""
import pytest

from tenantbench.validators.base import Policy
from tenantbench.validators.v1_regex import RegexValidator
from tenantbench.validators.v2_statement import StatementValidator
from tenantbench.validators.v3_scope import ScopeValidator

P = Policy(frozenset({"orders", "customers"}))
T = 3

CASES = [
    # (sql, V1, V2, V3)
    ("SELECT * FROM orders WHERE tenant_id = 3", True, True, True),
    ("SELECT * FROM orders", False, False, False),
    ("SELECT * FROM orders WHERE tenant_id = 3 OR 1=1", True, False, False),
    ("SELECT * FROM orders WHERE tenant_id = 4", True, False, False),
    ("SELECT * FROM orders o JOIN customers c ON c.customer_id = o.customer_id WHERE o.tenant_id = 3",
     True, False, False),
    ("SELECT * FROM orders o JOIN customers c ON c.customer_id = o.customer_id "
     "WHERE o.tenant_id = 3 AND c.tenant_id = 3", True, True, True),
    # K3: second set-operation branch unfiltered
    ("SELECT amount FROM orders WHERE tenant_id = 3 UNION SELECT amount FROM orders", True, True, False),
    # K5: CTE filtered, base table read again outside
    ("WITH c AS (SELECT * FROM orders WHERE tenant_id = 3) "
     "SELECT * FROM c JOIN orders o2 ON o2.order_id = c.order_id WHERE c.tenant_id = 3", True, False, False),
    # K7: unfiltered subquery
    ("SELECT * FROM orders WHERE tenant_id = 3 AND customer_id IN (SELECT customer_id FROM customers)",
     True, True, False),
    # K11: predicate only inside a comment
    ("SELECT * FROM orders -- tenant_id = 3", True, False, False),
]


@pytest.mark.parametrize("sql,v1,v2,v3", CASES)
def test_cases(sql, v1, v2, v3):
    assert RegexValidator().check(sql, P, T).accepted is v1
    assert StatementValidator().check(sql, P, T).accepted is v2
    assert ScopeValidator().check(sql, P, T).accepted is v3


def test_multiple_statements_rejected():
    sql = "SELECT * FROM orders WHERE tenant_id = 3; SELECT * FROM orders"
    assert not StatementValidator().check(sql, P, T).accepted
    assert not ScopeValidator().check(sql, P, T).accepted


# --- V4, V5, V6 -------------------------------------------------------------------------
from tenantbench.validators.v4_rewrite import RewriteValidator  # noqa: E402
from tenantbench.validators.v5_reference import ReferenceValidator  # noqa: E402
from tenantbench.validators.v6_sqlguardrail import SqlGuardrailValidator  # noqa: E402

PK = Policy(frozenset({"orders", "customers"}), known_tables=frozenset({"orders", "customers", "regions"}))

CASES_REF = [
    # (sql, V5 accepts)
    ("SELECT * FROM orders WHERE tenant_id = 3", True),
    ("SELECT * FROM orders o JOIN regions r ON r.id = o.region_id WHERE tenant_id = 3", True),
    ("SELECT amount FROM orders WHERE tenant_id = 3 UNION SELECT amount FROM orders", False),
    ("SELECT * FROM orders AS \"A\" JOIN orders AS a ON true WHERE \"A\".tenant_id = 3", False),
    ("SELECT * FROM orders o LEFT JOIN customers c ON c.id = o.customer_id AND c.tenant_id = 3 "
     "WHERE o.tenant_id = 3", True),
    ("SELECT * FROM orders o LEFT JOIN customers c ON c.id = o.customer_id AND o.tenant_id = 3 "
     "AND c.tenant_id = 3", False),
    ("SELECT * FROM orders WHERE tenant_id = 3 AND query_to_xml('select 1', true, true, '') IS NOT NULL", False),
    ("SELECT * FROM secrets WHERE tenant_id = 3", False),
    ("WITH c AS (SELECT * FROM orders WHERE tenant_id = 3) SELECT count(*) FROM c", True),
]


@pytest.mark.parametrize("sql,ok", CASES_REF)
def test_reference(sql, ok):
    assert ReferenceValidator().check(sql, PK, T).accepted is ok


def test_rewriter_scopes_every_read():
    d = RewriteValidator().check("SELECT amount FROM orders UNION SELECT amount FROM orders o2", PK, T)
    assert d.accepted and d.sql.count("tenant_id = 3") == 2


def test_sqlguardrail_runs():
    v = SqlGuardrailValidator()
    assert v.check("SELECT * FROM orders WHERE tenant_id = 3", PK, T).accepted
    assert not v.check("SELECT * FROM orders", PK, T).accepted
