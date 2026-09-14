"""Load processed San Antonio 311 records into PostgreSQL."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Iterable, Sequence
from importlib.resources import files
from pathlib import Path
from typing import Any

import psycopg
from psycopg import Connection

DATABASE_URL_ENV = "DATABASE_URL"
LOAD_COLUMNS = (
    "srnumber",
    "status",
    "location",
    "title",
    "department",
    "category",
    "cosa_tract_combo",
    "tract_name",
    "council_district",
    "median_household_income_rank",
    "overall_rank",
    "create_date",
    "due_date",
    "closed_date",
    "last_updated",
    "objectid",
    "xcoord",
    "ycoord",
    "longitude",
    "latitude",
    "coordinate_valid",
)

UPSERT_SQL = f"""
INSERT INTO service_requests ({", ".join(LOAD_COLUMNS)})
VALUES ({", ".join(["%s"] * len(LOAD_COLUMNS))})
ON CONFLICT (srnumber) DO UPDATE SET
    {", ".join(f"{column} = EXCLUDED.{column}" for column in LOAD_COLUMNS[1:])},
    loaded_at = now()
"""


def load_processed_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read and validate processed JSONL records before opening a database."""
    if not path.is_file():
        raise FileNotFoundError(f"Processed input does not exist: {path}")

    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            if not isinstance(record, dict):
                raise TypeError(f"Line {line_number} is not a JSON object")
            missing = [column for column in LOAD_COLUMNS if column not in record]
            if missing:
                raise ValueError(
                    f"Line {line_number} is missing columns: {', '.join(missing)}"
                )
            records.append(record)

    if not records:
        raise ValueError("Processed input contains no records")
    return records


def schema_sql() -> str:
    """Read the SQL schema bundled with the installed Python package."""
    schema = files("san_antonio_311").joinpath("sql/schema.sql")
    return schema.read_text(encoding="utf-8")


def ensure_schema(connection: Connection[Any]) -> None:
    """Create the table and indexes when they do not already exist."""
    with connection.cursor() as cursor:
        cursor.execute(schema_sql())


def upsert_records(
    connection: Connection[Any], records: Iterable[dict[str, Any]]
) -> int:
    """Insert new requests and update existing requests by ``srnumber``."""
    rows = [tuple(record[column] for column in LOAD_COLUMNS) for record in records]
    if not rows:
        return 0
    with connection.cursor() as cursor:
        cursor.executemany(UPSERT_SQL, rows)
    return len(rows)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse database loader options."""
    parser = argparse.ArgumentParser(
        description="Upsert processed San Antonio 311 records into PostgreSQL."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument(
        "--dsn",
        help=f"PostgreSQL connection string; defaults to ${DATABASE_URL_ENV}",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Load one processed snapshot into PostgreSQL as a single transaction."""
    args = parse_args(argv)
    dsn = args.dsn or os.getenv(DATABASE_URL_ENV)
    if not dsn:
        raise SystemExit(
            f"Database URL required: pass --dsn or set {DATABASE_URL_ENV}"
        )

    try:
        records = load_processed_jsonl(args.input)
        # The connection context commits on success and rolls back on failure.
        with psycopg.connect(dsn) as connection:
            ensure_schema(connection)
            loaded = upsert_records(connection, records)
    except (json.JSONDecodeError, OSError, psycopg.Error, TypeError, ValueError) as error:
        raise SystemExit(f"Database load failed: {error}") from error

    print(f"Upserted {loaded} records into service_requests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
