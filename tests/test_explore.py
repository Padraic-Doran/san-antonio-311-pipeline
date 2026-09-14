"""Unit tests for reusable exploratory analysis helpers."""

import pandas as pd
import pytest

from san_antonio_311.explore import (
    category_counts,
    convert_date_columns,
    duplicate_request_report,
    missing_values_report,
    summarize_dataset,
)


@pytest.fixture
def sample_df() -> pd.DataFrame:
    """Create a small table containing duplicates, missing data, and epoch dates."""
    return pd.DataFrame(
        {
            "SRNUMBER": ["100", "100", "200"],
            "CATEGORY": ["Animals", "Animals", None],
            "CREATE_DATE": [1_700_000_000_000, 1_700_000_001_000, None],
            "DUE_DATE": [None, None, None],
            "CLOSED_DATE": [None, None, 1_700_000_002_000],
            "LAST_UPDATED": [1_700_000_003_000] * 3,
        }
    )


def test_summarize_dataset(sample_df: pd.DataFrame) -> None:
    summary = summarize_dataset(sample_df)
    assert summary["rows"] == 3
    assert summary["columns"] == 6
    assert summary["column_names"][0] == "SRNUMBER"


def test_missing_values_report(sample_df: pd.DataFrame) -> None:
    report = missing_values_report(sample_df)
    assert report.loc["DUE_DATE", "missing_count"] == 3
    assert report.loc["DUE_DATE", "missing_percent"] == 100


def test_duplicate_request_report(sample_df: pd.DataFrame) -> None:
    duplicates = duplicate_request_report(sample_df)
    assert duplicates["SRNUMBER"].tolist() == ["100", "100"]


def test_convert_date_columns_returns_a_copy(sample_df: pd.DataFrame) -> None:
    converted = convert_date_columns(sample_df)
    assert pd.api.types.is_datetime64_any_dtype(converted["CREATE_DATE"])
    assert str(converted["CREATE_DATE"].dt.tz) == "UTC"
    assert not pd.api.types.is_datetime64_any_dtype(sample_df["CREATE_DATE"])


def test_category_counts(sample_df: pd.DataFrame) -> None:
    counts = category_counts(sample_df, top_n=1)
    assert counts.to_dict() == {"Animals": 2}


def test_exploration_functions_reject_missing_columns() -> None:
    with pytest.raises(KeyError, match="CATEGORY"):
        category_counts(pd.DataFrame({"STATUS": ["OPEN"]}))
    with pytest.raises(ValueError, match="top_n"):
        category_counts(pd.DataFrame({"CATEGORY": ["Animals"]}), top_n=0)
