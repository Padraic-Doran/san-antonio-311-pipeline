"""Download a reproducible sample of San Antonio 311 service requests."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

SERVICE_URL = (
    "https://services.arcgis.com/g1fRTDLeMgspWrYp/arcgis/rest/services/"
    "311_Open_Service_Calls/FeatureServer/0/query"
)
DEFAULT_OUTPUT = Path("data/raw/service_requests.jsonl")
OUT_FIELDS = (
    "SRNUMBER,STATUS,LOCATION,TITLE,DEPARTMENT,CATEGORY,COSA_TRACT_COMBO,"
    "TRACT_NAME,COUNCIL_DISTRICT,MEDIAN_HOUSEHOLD_INCOME_RANK,OVERALL_RANK,"
    "CREATE_DATE,DUE_DATE,CLOSED_DATE,LAST_UPDATED,OBJECTID,XCOORD,YCOORD"
)


def build_query_url(limit: int) -> str:
    """Build a deterministic ArcGIS query URL for a bounded sample."""
    if not 1 <= limit <= 2_000:
        raise ValueError("limit must be between 1 and 2000")

    params = {
        "where": "1=1",
        "outFields": OUT_FIELDS,
        "returnGeometry": "true",
        "outSR": "4326",
        "orderByFields": "OBJECTID ASC",
        "resultRecordCount": str(limit),
        "f": "json",
    }
    return f"{SERVICE_URL}?{urlencode(params)}"


def fetch_features(
    limit: int,
    opener: Callable[..., Any] = urlopen,
) -> list[dict[str, Any]]:
    """Fetch and flatten a page of features from the official public service."""
    request_url = build_query_url(limit)
    with opener(request_url, timeout=30) as response:
        payload = json.load(response)

    if "error" in payload:
        message = payload["error"].get("message", "ArcGIS query failed")
        raise RuntimeError(message)

    features = payload.get("features")
    if not isinstance(features, list):
        raise TypeError("ArcGIS response did not contain a features list")

    records: list[dict[str, Any]] = []
    for feature in features:
        record = dict(feature.get("attributes") or {})
        geometry = feature.get("geometry") or {}
        record["LONGITUDE"] = geometry.get("x")
        record["LATITUDE"] = geometry.get("y")
        records.append(record)
    return records


def write_jsonl(records: Sequence[dict[str, Any]], output: Path) -> None:
    """Write records as newline-delimited JSON."""
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    with temporary.open("w", encoding="utf-8") as destination:
        for record in records:
            destination.write(json.dumps(record, sort_keys=True) + "\n")
    temporary.replace(output)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download recent San Antonio 311 service requests."
    )
    parser.add_argument("--limit", type=int, default=100, help="1-2000 records")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        records = fetch_features(args.limit)
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise SystemExit(f"Ingestion failed: {error}") from error

    write_jsonl(records, args.output)
    print(f"Wrote {len(records)} records to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
