"""Download validated snapshots of recent San Antonio 311 service requests."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SERVICE_URL = (
    "https://services.arcgis.com/g1fRTDLeMgspWrYp/arcgis/rest/services/"
    "311_Open_Service_Calls/FeatureServer/0/query"
)
MAX_PAGE_SIZE = 2_000
OUT_FIELDS = (
    "SRNUMBER,STATUS,LOCATION,TITLE,DEPARTMENT,CATEGORY,COSA_TRACT_COMBO,"
    "TRACT_NAME,COUNCIL_DISTRICT,MEDIAN_HOUSEHOLD_INCOME_RANK,OVERALL_RANK,"
    "CREATE_DATE,DUE_DATE,CLOSED_DATE,LAST_UPDATED,OBJECTID,XCOORD,YCOORD"
)
REQUIRED_FIELDS = ("SRNUMBER", "STATUS", "CREATE_DATE", "OBJECTID")


def positive_integer(value: str) -> int:
    """Parse a positive command-line integer."""
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def build_query_url(page_size: int, offset: int = 0) -> str:
    """Build one deterministic, paginated ArcGIS query URL."""
    if not 1 <= page_size <= MAX_PAGE_SIZE:
        raise ValueError(f"page_size must be between 1 and {MAX_PAGE_SIZE}")
    if offset < 0:
        raise ValueError("offset cannot be negative")

    params = {
        "where": "1=1",
        "outFields": OUT_FIELDS,
        "returnGeometry": "true",
        "outSR": "4326",
        "orderByFields": "OBJECTID ASC",
        "resultOffset": str(offset),
        "resultRecordCount": str(page_size),
        "f": "json",
    }
    return f"{SERVICE_URL}?{urlencode(params)}"


def _read_page(
    page_size: int,
    offset: int,
    opener: Callable[..., Any],
) -> dict[str, Any]:
    """Request and validate the outer structure of one ArcGIS response page."""
    request = Request(
        build_query_url(page_size, offset),
        headers={"User-Agent": "san-antonio-311-pipeline/0.1"},
    )
    with opener(request, timeout=30) as response:
        payload = json.load(response)

    if not isinstance(payload, dict):
        raise TypeError("ArcGIS response must be a JSON object")
    if "error" in payload:
        error = payload["error"]
        message = error.get("message") if isinstance(error, dict) else str(error)
        raise RuntimeError(message or "ArcGIS query failed")
    if not isinstance(payload.get("features"), list):
        raise TypeError("ArcGIS response did not contain a features list")
    return payload


def _flatten_feature(feature: Any) -> dict[str, Any]:
    """Validate one ArcGIS feature and flatten its attributes and geometry."""
    if not isinstance(feature, dict):
        raise TypeError("Each ArcGIS feature must be a JSON object")
    attributes = feature.get("attributes")
    if not isinstance(attributes, dict):
        raise TypeError("Each ArcGIS feature must contain an attributes object")

    missing = [field for field in REQUIRED_FIELDS if field not in attributes]
    if missing:
        raise ValueError(f"Feature is missing required fields: {', '.join(missing)}")
    empty = [field for field in REQUIRED_FIELDS if attributes[field] is None]
    if empty:
        raise ValueError(f"Feature has null required fields: {', '.join(empty)}")

    geometry = feature.get("geometry")
    if geometry is not None and not isinstance(geometry, dict):
        raise TypeError("Feature geometry must be an object or null")
    geometry = geometry or {}
    longitude = geometry.get("x")
    latitude = geometry.get("y")
    for name, coordinate in (("longitude", longitude), ("latitude", latitude)):
        if coordinate is not None and not isinstance(coordinate, (int, float)):
            raise TypeError(f"Feature {name} must be numeric or null")

    record = dict(attributes)
    record["LONGITUDE"] = longitude
    record["LATITUDE"] = latitude
    return record


def fetch_features(
    limit: int,
    opener: Callable[..., Any] = urlopen,
    page_size: int = MAX_PAGE_SIZE,
) -> list[dict[str, Any]]:
    """Fetch up to ``limit`` validated features across one or more API pages."""
    if limit < 1:
        raise ValueError("limit must be at least 1")
    if not 1 <= page_size <= MAX_PAGE_SIZE:
        raise ValueError(f"page_size must be between 1 and {MAX_PAGE_SIZE}")

    records: list[dict[str, Any]] = []
    while len(records) < limit:
        requested = min(page_size, limit - len(records))
        payload = _read_page(requested, len(records), opener)
        features = payload["features"]
        if not features:
            break
        records.extend(_flatten_feature(feature) for feature in features)
        # A short page means the service has no more matching records.
        if len(features) < requested:
            break
    return records[:limit]


def default_output_path(now: datetime | None = None) -> Path:
    """Create a timestamped landing-zone path so snapshots are never overwritten."""
    timestamp = (now or datetime.now(UTC)).astimezone(UTC)
    partition = timestamp.strftime("extracted_at=%Y-%m-%dT%H-%M-%S.%fZ")
    return Path("data/raw") / partition / "service_requests.jsonl"


def write_jsonl(records: Sequence[dict[str, Any]], output: Path) -> None:
    """Atomically write records as newline-delimited JSON."""
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as destination:
            temporary_path = Path(destination.name)
            for record in records:
                destination.write(json.dumps(record, sort_keys=True) + "\n")
        os.replace(temporary_path, output)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def write_metadata(
    output: Path,
    requested_records: int,
    actual_records: int,
    extracted_at: datetime,
) -> Path:
    """Write provenance metadata beside a snapshot and return its path."""
    metadata_path = output.with_name("metadata.json")
    metadata = {
        "actual_records": actual_records,
        "extracted_at_utc": extracted_at.astimezone(UTC).isoformat(),
        "normalized_during_ingestion": ["geometry flattened to LONGITUDE/LATITUDE"],
        "requested_records": requested_records,
        "source_url": SERVICE_URL,
    }
    write_jsonl([metadata], metadata_path)
    return metadata_path


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line options."""
    parser = argparse.ArgumentParser(
        description="Download recent San Antonio 311 service requests."
    )
    parser.add_argument("--limit", type=positive_integer, default=100)
    parser.add_argument(
        "--page-size",
        type=positive_integer,
        default=MAX_PAGE_SIZE,
        help=f"records per API request, at most {MAX_PAGE_SIZE}",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="optional JSONL path; defaults to a timestamped snapshot directory",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Download, validate, and persist one recent 311 snapshot."""
    args = parse_args(argv)
    extracted_at = datetime.now(UTC)
    output = args.output or default_output_path(extracted_at)
    try:
        records = fetch_features(args.limit, page_size=args.page_size)
        write_jsonl(records, output)
        metadata_path = write_metadata(
            output, args.limit, len(records), extracted_at=extracted_at
        )
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise SystemExit(f"Ingestion failed: {error}") from error

    print(f"Wrote {len(records)} records to {output}")
    print(f"Wrote extraction metadata to {metadata_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
