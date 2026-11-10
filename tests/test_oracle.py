"""Oracle smoke test on a two-tenant toy table. Needs the container from scripts/start_pg.sh."""
import os

import psycopg
import pytest

from tenantbench import oracle

CONN = os.environ.get("TB_CONN", "postgresql://postgres:tenantbench@127.0.0.1:55432/tenantbench")

SETUP = """
DROP SCHEMA IF EXISTS toy CASCADE;
CREATE SCHEMA toy;
CREATE TABLE toy.orders (order_id int PRIMARY KEY, tenant_id int NOT NULL, amount numeric);
INSERT INTO toy.orders VALUES (1, 1, 10), (2, 1, 20), (3, 2, 300);
ALTER TABLE toy.orders ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tb_all') THEN CREATE ROLE tb_all BYPASSRLS; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tb_tenant') THEN CREATE ROLE tb_tenant; END IF;
END $$;
CREATE POLICY tenant_rows ON toy.orders USING (tenant_id = current_setting('tb.tenant')::int);
GRANT USAGE ON SCHEMA toy TO tb_all, tb_tenant;
GRANT SELECT ON ALL TABLES IN SCHEMA toy TO tb_all, tb_tenant;
"""


@pytest.fixture(scope="module")
def db():
    try:
        with psycopg.connect(CONN, autocommit=True) as c:
            c.execute(SETUP)
    except psycopg.OperationalError:
        pytest.skip("oracle database not running")
    yield CONN
    with psycopg.connect(CONN, autocommit=True) as c:
        c.execute("DROP SCHEMA toy CASCADE")


def test_filtered_query_does_not_leak(db):
    v = oracle.leaks(db, "SELECT sum(amount) FROM toy.orders WHERE tenant_id = 1",
                     "SELECT sum(amount) FROM toy.orders WHERE tenant_id = 1", 1)
    assert v.leaks is False


def test_unfiltered_aggregate_leaks(db):
    v = oracle.leaks(db, "SELECT sum(amount) FROM toy.orders", "SELECT sum(amount) FROM toy.orders", 1)
    assert v.leaks is True


def test_error_is_not_a_leak(db):
    v = oracle.leaks(db, "SELECT nope FROM toy.orders", "SELECT nope FROM toy.orders", 1)
    assert v.leaks is None and "UndefinedColumn" in v.detail


def test_write_is_refused(db):
    out = oracle.run(db, "tb_all", "DELETE FROM toy.orders")
    assert not out.ok
