"""Optional integration test against a real PostgreSQL service."""

import os
from typing import Any

import psycopg
import pytest

from san_antonio_311.database import LOAD_COLUMNS, ensure_schema, upsert_records

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set",
)


def processed_record(**overrides: Any) -> dict[str, Any]:
    """Build a complete row without importing helpers from another test module."""
    record = {column: None for column in LOAD_COLUMNS}
    record.update(
        {
            "srnumber": "102000000001",
            "status": "OPEN",
            "create_date": "2026-09-14T12:00:00.000Z",
            "last_updated": "2026-09-14T12:30:00.000Z",
            "objectid": 1,
            "coordinate_valid": True,
        }
    )
    record.update(overrides)
    return record


def test_postgres_schema_and_upsert_are_idempotent() -> None:
    assert TEST_DATABASE_URL is not None
    with psycopg.connect(TEST_DATABASE_URL) as connection:
        ensure_schema(connection)
        with connection.cursor() as cursor:
            cursor.execute("TRUNCATE TABLE service_requests")
        upsert_records(connection, [processed_record(status="OPEN")])
        upsert_records(connection, [processed_record(status="CLOSED")])
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*), max(status) FROM service_requests")
            assert cursor.fetchone() == (1, "CLOSED")
