"""Tests for the landing-to-processed transformation stage."""

import json
from pathlib import Path

import pandas as pd
import pytest

from san_antonio_311.transform import (
    default_output_path,
    load_jsonl,
    main,
    transform_records,
    write_processed_jsonl,
    write_quality_report,
)


@pytest.fixture
def landing_df() -> pd.DataFrame:
    """Provide two versions of one request plus one distinct request."""
    return pd.DataFrame(
        {
            "SRNUMBER": [" 100 ", "100", "200"],
            "STATUS": ["open", " closed ", "OPEN"],
            "CATEGORY": [" Animals ", "Animals", ""],
            "CREATE_DATE": [1_700_000_000_000] * 3,
            "DUE_DATE": [None] * 3,
            "CLOSED_DATE": [None, 1_700_000_002_000, None],
            "LAST_UPDATED": [
                1_700_000_001_000,
                1_700_000_003_000,
                1_700_000_004_000,
            ],
            "OBJECTID": [1, 2, 3],
            "LONGITUDE": [-98.49, -98.49, 999.0],
            "LATITUDE": [29.42, 29.42, None],
        }
    )


def test_transform_records_normalizes_and_deduplicates(
    landing_df: pd.DataFrame,
) -> None:
    processed, quality = transform_records(landing_df)
    assert processed["srnumber"].tolist() == ["100", "200"]
    assert processed.loc[0, "status"] == "CLOSED"
    assert pd.isna(processed.loc[1, "category"])
    assert str(processed["create_date"].dt.tz) == "UTC"
    assert processed["coordinate_valid"].tolist() == [True, False]
    assert quality == {
        "duplicate_rows_removed": 1,
        "input_rows": 3,
        "invalid_or_missing_coordinates": 1,
        "missing_categories": 1,
        "output_rows": 2,
    }
    # The transformation returns a new table instead of modifying landing data.
    assert landing_df.loc[0, "STATUS"] == "open"


def test_transform_records_requires_expected_schema(landing_df: pd.DataFrame) -> None:
    with pytest.raises(KeyError, match="SRNUMBER"):
        transform_records(landing_df.drop(columns="SRNUMBER"))


def test_load_jsonl_preserves_request_number_as_text(tmp_path: Path) -> None:
    source = tmp_path / "input.jsonl"
    source.write_text('{"SRNUMBER":"001","STATUS":"OPEN"}\n', encoding="utf-8")
    loaded = load_jsonl(source)
    assert loaded.loc[0, "SRNUMBER"] == "001"


def test_load_jsonl_rejects_missing_and_empty_files(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_jsonl(tmp_path / "missing.jsonl")
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="no records"):
        load_jsonl(empty)


def test_default_output_path_mirrors_raw_partition() -> None:
    source = Path("data/raw/extracted_at=2026-09-14/input.jsonl")
    assert default_output_path(source) == Path(
        "data/processed/extracted_at=2026-09-14/input.jsonl"
    )


def test_writers_create_jsonl_and_quality_report(
    tmp_path: Path, landing_df: pd.DataFrame
) -> None:
    processed, quality = transform_records(landing_df)
    output = tmp_path / "processed" / "requests.jsonl"
    write_processed_jsonl(processed, output)
    report_path = write_quality_report(quality, output)
    first = json.loads(output.read_text(encoding="utf-8").splitlines()[0])
    assert first["create_date"].endswith("Z")
    assert json.loads(report_path.read_text())["output_rows"] == 2


def test_main_runs_end_to_end(tmp_path: Path, landing_df: pd.DataFrame) -> None:
    source = tmp_path / "raw" / "requests.jsonl"
    source.parent.mkdir()
    landing_df.to_json(source, orient="records", lines=True)
    output = tmp_path / "processed" / "requests.jsonl"
    assert main(["--input", str(source), "--output", str(output)]) == 0
    assert output.exists()
    assert output.with_name("quality_report.json").exists()
