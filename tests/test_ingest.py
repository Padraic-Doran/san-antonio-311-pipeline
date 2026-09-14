"""Unit tests for the ArcGIS ingestion boundary and local JSONL writer."""

import io
import json
from pathlib import Path
from typing import Self

import pytest

from san_antonio_311.ingest import build_query_url, fetch_features, write_jsonl


class FakeResponse(io.StringIO):
    """Provide the context-manager behavior returned by ``urlopen``."""

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def test_build_query_url_enforces_service_limit() -> None:
    # Check both reproducibility and protection from oversized API requests.
    assert "resultRecordCount=25" in build_query_url(25)
    assert "orderByFields=OBJECTID+ASC" in build_query_url(25)
    with pytest.raises(ValueError):
        build_query_url(2_001)


def test_fetch_features_flattens_geometry() -> None:
    # This fixture mirrors the relevant portion of an ArcGIS query response.
    payload = {
        "features": [
            {
                "attributes": {"SRNUMBER": "102000000001", "STATUS": "OPEN"},
                "geometry": {"x": -98.49, "y": 29.42},
            }
        ]
    }

    def opener(url: str, timeout: int) -> FakeResponse:
        # Injecting the opener keeps the unit test offline and deterministic.
        assert url.startswith("https://services.arcgis.com/")
        assert timeout == 30
        return FakeResponse(json.dumps(payload))

    assert fetch_features(1, opener=opener) == [
        {
            "SRNUMBER": "102000000001",
            "STATUS": "OPEN",
            "LONGITUDE": -98.49,
            "LATITUDE": 29.42,
        }
    ]


def test_write_jsonl(tmp_path: Path) -> None:
    # pytest supplies an isolated directory so the real data folder is untouched.
    output = tmp_path / "raw" / "requests.jsonl"
    write_jsonl([{"OBJECTID": 1}, {"OBJECTID": 2}], output)
    assert output.read_text(encoding="utf-8").splitlines() == [
        '{"OBJECTID": 1}',
        '{"OBJECTID": 2}',
    ]
