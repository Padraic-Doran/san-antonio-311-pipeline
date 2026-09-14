"""Reusable exploratory analysis helpers for San Antonio 311 records."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pandas as pd

DATE_COLUMNS = ("CREATE_DATE", "DUE_DATE", "CLOSED_DATE", "LAST_UPDATED")


def _require_columns(df: pd.DataFrame, columns: Sequence[str]) -> None:
    """Raise a clear error when an analysis receives the wrong schema."""
    missing = [column for column in columns if column not in df.columns]
    if missing:
        names = ", ".join(missing)
        raise KeyError(f"DataFrame is missing required columns: {names}")


def summarize_dataset(df: pd.DataFrame) -> dict[str, Any]:
    """Return the dataset's dimensions, column names, and pandas data types."""
    return {
        "rows": len(df),
        "columns": len(df.columns),
        "column_names": df.columns.tolist(),
        "data_types": df.dtypes.astype(str).to_dict(),
    }


def missing_values_report(df: pd.DataFrame) -> pd.DataFrame:
    """Count and calculate the percentage of missing values in every column."""
    counts = df.isna().sum()
    # Define empty-data percentages as zero instead of returning NaN values.
    percentages = counts.mul(100).div(len(df)) if len(df) else counts.astype(float)
    report = pd.DataFrame(
        {
            "missing_count": counts,
            "missing_percent": percentages,
        }
    )
    return report.sort_values(
        by=["missing_count", "missing_percent"], ascending=False
    )


def duplicate_request_report(df: pd.DataFrame) -> pd.DataFrame:
    """Return every row whose service-request number appears more than once."""
    _require_columns(df, ["SRNUMBER"])
    # Missing identifiers are a validation concern, not a group of duplicates.
    duplicates = df["SRNUMBER"].notna() & df.duplicated(
        subset=["SRNUMBER"], keep=False
    )
    return df.loc[duplicates].sort_values("SRNUMBER").copy()


def convert_date_columns(
    df: pd.DataFrame,
    columns: Sequence[str] = DATE_COLUMNS,
) -> pd.DataFrame:
    """Convert ArcGIS epoch-millisecond fields to timezone-aware UTC timestamps."""
    _require_columns(df, columns)
    converted = df.copy()
    for column in columns:
        converted[column] = pd.to_datetime(
            converted[column], unit="ms", utc=True, errors="coerce"
        )
    return converted


def category_counts(df: pd.DataFrame, top_n: int = 10) -> pd.Series:
    """Return the most frequent 311 categories, including missing categories."""
    _require_columns(df, ["CATEGORY"])
    if top_n < 1:
        raise ValueError("top_n must be at least 1")
    counts = df["CATEGORY"].value_counts(dropna=False).head(top_n)
    return counts.rename("requests")
