"""The database refusing to hold a dishonest row.

Each promise in DATABASE.md §9 is a CHECK constraint, and each one is asserted
here against a real migrated Postgres. Unit tests prove the Python objects guard
themselves; these prove the guard survives a script, a psql session, or a future
service that forgets.

Skipped unless ``PDE_TEST_DATABASE_URL`` points at a migrated database. CI sets
it; locally, run docker compose and `alembic upgrade head` first.
"""

from __future__ import annotations

import os

import pytest

psycopg = pytest.importorskip("psycopg")

DSN = os.environ.get("PDE_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="PDE_TEST_DATABASE_URL not set")


@pytest.fixture
def conn():
    with psycopg.connect(DSN) as connection:  # type: ignore[arg-type]
        yield connection
        connection.rollback()


def _rejects(conn, sql: str, constraint: str) -> None:
    with conn.cursor() as cur, pytest.raises(psycopg.errors.CheckViolation) as excinfo:
        cur.execute(sql)
    assert constraint in str(excinfo.value)
    conn.rollback()


def test_a_prohibited_source_cannot_be_marked_storable(conn):
    _rejects(
        conn,
        """INSERT INTO data_sources (id, key, name, licence_class, may_store_values,
                                     created_at, updated_at)
           VALUES (gen_random_uuid(), 'src_test', 'test', 'prohibited', true, now(), now())""",
        "prohibited_is_never_storable",
    )


def test_an_unverified_rule_cannot_be_active(conn):
    # A number we could not confirm must not reach a calculation someone spends money on.
    _rejects(
        conn,
        """INSERT INTO rules (id, jurisdiction, name, value, effective_from, source_url,
                              verification, active, version, created_at, updated_at)
           VALUES (gen_random_uuid(), 'ON', 'test.rule', '{}'::jsonb, '2026-01-01',
                   'https://example.invalid', 'unverified', true, 1, now(), now())""",
        "unverified_is_never_active",
    )


def test_an_unavailable_fact_must_say_why(conn):
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO data_sources (id, key, name, licence_class, may_store_values,
                                         created_at, updated_at)
               VALUES (gen_random_uuid(), 'src_tmp', 'tmp', 'open', true, now(), now())
               RETURNING id"""
        )
        source_id = cur.fetchone()[0]
    _rejects(
        conn,
        f"""INSERT INTO data_provenance (id, data_source_id, source_class, retrieved_at,
                                         confidence)
            VALUES (gen_random_uuid(), '{source_id}', 'unavailable', now(), 0)""",
        "unavailable_states_why",
    )


def test_an_effective_range_cannot_run_backwards(conn):
    _rejects(
        conn,
        """INSERT INTO rules (id, jurisdiction, name, value, effective_from, effective_to,
                              source_url, verification, active, version, created_at, updated_at)
           VALUES (gen_random_uuid(), 'ON', 'test.rule', '{}'::jsonb, '2026-05-01', '2026-04-01',
                   'https://example.invalid', 'primary', true, 1, now(), now())""",
        "effective_range_is_ordered",
    )


def test_postgis_is_available_and_geography_columns_exist(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT PostGIS_Version()")
        assert cur.fetchone()[0]
        cur.execute(
            """SELECT count(*) FROM information_schema.columns
               WHERE table_name IN ('properties', 'locations', 'comparables')
                 AND column_name = 'geom'"""
        )
        assert cur.fetchone()[0] == 3


def test_every_expected_table_exists(conn):
    expected = {
        "users",
        "user_profiles",
        "financial_profiles",
        "buyer_preferences",
        "audit_logs",
        "properties",
        "property_sources",
        "property_attributes",
        "property_price_history",
        "locations",
        "location_metrics",
        "saved_properties",
        "comparables",
        "data_sources",
        "data_provenance",
        "rules",
        "rule_sets",
        "market_snapshots",
        "property_analyses",
        "analysis_scores",
        "analysis_factors",
        "risk_flags",
        "calculation_traces",
        "comparable_scores",
        "financial_scenarios",
        "ai_judgements",
        "analysis_judgements",
        "ai_reports",
        "property_comparisons",
    }
    with conn.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        )
        present = {row[0] for row in cur.fetchall()}
    assert expected <= present, f"missing tables: {sorted(expected - present)}"


def test_money_columns_are_never_floating_point(conn):
    """ADR 0001 §8. A float mortgage balance is wrong by the end of the amortization.

    Two shapes are legitimate: ``bigint`` for ordinary money, and ``bytea`` for the
    financial-profile columns, which are ciphertext at rest and hold integer cents
    once decrypted. Anything else — and in particular ``double precision`` or
    ``real`` — is the bug this test exists to catch.
    """
    with conn.cursor() as cur:
        cur.execute(
            """SELECT table_name, column_name, data_type
               FROM information_schema.columns
               WHERE table_schema = 'public' AND column_name LIKE '%%_cents'"""
        )
        rows = cur.fetchall()
    assert rows, "no money columns found — the query is wrong, not the schema"
    offenders = [row for row in rows if row[2] not in {"bigint", "bytea"}]
    assert not offenders, f"money columns must be bigint (or bytea when encrypted): {offenders}"

    encrypted = {row[1] for row in rows if row[2] == "bytea"}
    assert "gross_annual_income_cents" in encrypted, "income must be opaque at rest"
