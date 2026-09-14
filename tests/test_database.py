"""Unit tests for PostgreSQL loading and processed-file validation."""

import json
from pathlib import Path
from typing import Any, Self

import pytest

from san_antonio_311.database import (
    LOAD_COLUMNS,
    ensure_schema,
    load_processed_jsonl,
    main,
    schema_sql,
    upsert_records,
)


def processed_record(**overrides: Any) -> dict[str, Any]:
    """Build one complete processed record."""
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


class FakeCursor:
    def __init__(self) -> None:
        self.executed: list[Any] = []

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, query: str) -> None:
        self.executed.append(query)

    def executemany(self, query: str, rows: list[tuple[Any, ...]]) -> None:
        self.executed.append((query, rows))


class FakeConnection:
    def __init__(self) -> None:
        self.cursors: list[FakeCursor] = []

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def cursor(self) -> FakeCursor:
        cursor = FakeCursor()
        self.cursors.append(cursor)
        return cursor


def test_load_processed_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "processed.jsonl"
    expected = processed_record(srnumber="001")
    path.write_text(json.dumps(expected) + "\n", encoding="utf-8")
    assert load_processed_jsonl(path) == [expected]


def test_load_processed_jsonl_rejects_missing_column(tmp_path: Path) -> None:
    path = tmp_path / "processed.jsonl"
    record = processed_record()
    del record["status"]
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="status"):
        load_processed_jsonl(path)


def test_load_processed_jsonl_rejects_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "processed.jsonl"
    path.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="no records"):
        load_processed_jsonl(path)


def test_schema_and_upsert_use_expected_sql() -> None:
    connection = FakeConnection()
    ensure_schema(connection)  # type: ignore[arg-type]
    assert "CREATE TABLE IF NOT EXISTS service_requests" in schema_sql()
    assert "CREATE TABLE" in connection.cursors[0].executed[0]

    assert upsert_records(connection, [processed_record()]) == 1  # type: ignore[arg-type]
    query, rows = connection.cursors[1].executed[0]
    assert "ON CONFLICT (srnumber) DO UPDATE" in query
    assert rows[0][0] == "102000000001"


def test_upsert_records_accepts_empty_iterable() -> None:
    assert upsert_records(FakeConnection(), []) == 0  # type: ignore[arg-type]


def test_main_requires_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(SystemExit, match="Database URL required"):
        main(["--input", "unused.jsonl"])


def test_main_loads_records_with_injected_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "processed.jsonl"
    path.write_text(json.dumps(processed_record()) + "\n", encoding="utf-8")
    connection = FakeConnection()
    monkeypatch.setattr("san_antonio_311.database.psycopg.connect", lambda dsn: connection)
    assert main(["--input", str(path), "--dsn", "postgresql://test"]) == 0
    assert len(connection.cursors) == 2
