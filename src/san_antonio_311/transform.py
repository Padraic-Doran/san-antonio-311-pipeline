"""Clean landing-zone 311 records into an analysis-ready dataset."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pandas as pd

from san_antonio_311.explore import DATE_COLUMNS, convert_date_columns

REQUIRED_COLUMNS = (
    "SRNUMBER",
    "STATUS",
    "CATEGORY",
    "CREATE_DATE",
    "LAST_UPDATED",
    "OBJECTID",
    "LONGITUDE",
    "LATITUDE",
)


def load_jsonl(path: Path) -> pd.DataFrame:
    """Load a non-empty landing-zone JSONL file into a DataFrame."""
    if not path.is_file():
        raise FileNotFoundError(f"Input file does not exist: {path}")
    if path.stat().st_size == 0:
        raise ValueError("Input dataset contains no records")
    frame = pd.read_json(path, lines=True, dtype={"SRNUMBER": "string"})
    if frame.empty:
        raise ValueError("Input dataset contains no records")
    return frame


def _require_columns(df: pd.DataFrame, columns: Sequence[str]) -> None:
    """Fail early when the landing schema is incomplete."""
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise KeyError(f"Input is missing required columns: {', '.join(missing)}")


def _clean_text_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Trim text and replace empty strings with pandas missing values."""
    cleaned = df.copy()
    text_columns = cleaned.select_dtypes(include=["object", "string"]).columns
    for column in text_columns:
        cleaned[column] = cleaned[column].astype("string").str.strip()
        cleaned[column] = cleaned[column].replace("", pd.NA)
    return cleaned


def transform_records(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Validate, normalize, and deduplicate one landing-zone snapshot."""
    _require_columns(df, REQUIRED_COLUMNS)
    _require_columns(df, DATE_COLUMNS)

    input_rows = len(df)
    cleaned = _clean_text_columns(df)
    cleaned["STATUS"] = cleaned["STATUS"].str.upper()
    cleaned = convert_date_columns(cleaned)

    # Keep the most recently updated version when one request appears repeatedly.
    cleaned = cleaned.sort_values(
        by=["SRNUMBER", "LAST_UPDATED", "OBJECTID"],
        na_position="first",
    )
    cleaned = cleaned.drop_duplicates(subset=["SRNUMBER"], keep="last")

    # Python-style names are easier to query consistently in pandas and SQL.
    cleaned = cleaned.rename(columns=str.lower).reset_index(drop=True)
    coordinate_valid = (
        cleaned["longitude"].between(-180, 180, inclusive="both")
        & cleaned["latitude"].between(-90, 90, inclusive="both")
    )
    cleaned["coordinate_valid"] = coordinate_valid
    # Preserve the quality flag but prevent invalid coordinates entering analytics.
    cleaned.loc[~coordinate_valid, ["longitude", "latitude"]] = pd.NA

    quality = {
        "duplicate_rows_removed": input_rows - len(cleaned),
        "input_rows": input_rows,
        "invalid_or_missing_coordinates": int((~coordinate_valid).sum()),
        "missing_categories": int(cleaned["category"].isna().sum()),
        "output_rows": len(cleaned),
    }
    return cleaned, quality


def default_output_path(input_path: Path) -> Path:
    """Mirror a raw snapshot path under the processed data directory."""
    parts = list(input_path.parts)
    if "raw" in parts:
        parts[parts.index("raw")] = "processed"
        return Path(*parts)
    return input_path.with_name(f"{input_path.stem}_processed.jsonl")


def _atomic_write_text(content: str, output: Path) -> None:
    """Replace a text file only after its complete contents are on disk."""
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
            destination.write(content)
        os.replace(temporary_path, output)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def write_processed_jsonl(df: pd.DataFrame, output: Path) -> None:
    """Write an analysis-ready DataFrame as JSONL with ISO-8601 dates."""
    content = df.to_json(
        orient="records",
        lines=True,
        date_format="iso",
        date_unit="ms",
    )
    _atomic_write_text(content, output)


def write_quality_report(quality: dict[str, Any], output: Path) -> Path:
    """Write transformation counts beside the processed dataset."""
    report_path = output.with_name("quality_report.json")
    _atomic_write_text(json.dumps(quality, indent=2, sort_keys=True) + "\n", report_path)
    return report_path


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse transformation command-line options."""
    parser = argparse.ArgumentParser(
        description="Clean a San Antonio 311 landing-zone snapshot."
    )
    parser.add_argument("--input", type=Path, required=True, help="input JSONL file")
    parser.add_argument(
        "--output",
        type=Path,
        help="optional processed JSONL path; defaults to the matching processed path",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Load, transform, and persist one analysis-ready snapshot."""
    args = parse_args(argv)
    output = args.output or default_output_path(args.input)
    try:
        source = load_jsonl(args.input)
        processed, quality = transform_records(source)
        write_processed_jsonl(processed, output)
        report_path = write_quality_report(quality, output)
    except (KeyError, OSError, TypeError, ValueError) as error:
        raise SystemExit(f"Transformation failed: {error}") from error

    print(f"Wrote {len(processed)} processed records to {output}")
    print(f"Wrote quality report to {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
