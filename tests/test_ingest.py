"""Unit and integration tests for the 311 ingestion workflow."""

import io
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self
from urllib.parse import parse_qs, urlparse

import pytest

from san_antonio_311.ingest import (
    build_query_url,
    default_output_path,
    fetch_features,
    main,
    parse_args,
    write_jsonl,
    write_metadata,
)


class FakeResponse(io.StringIO):
    """Provide the context-manager behavior returned by ``urlopen``."""

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def feature(object_id: int, **overrides: Any) -> dict[str, Any]:
    """Build a valid API feature that tests can selectively modify."""
    attributes = {
        "SRNUMBER": f"102{object_id:09d}",
        "STATUS": "OPEN",
        "CREATE_DATE": 1_700_000_000_000,
        "OBJECTID": object_id,
    }
    attributes.update(overrides)
    return {
        "attributes": attributes,
        "geometry": {"x": -98.49, "y": 29.42},
    }


def fake_opener_for_pages(
    pages: dict[int, list[dict[str, Any]]],
) -> Any:
    """Return an opener that chooses a response using ArcGIS's result offset."""

    def opener(request: Any, timeout: int) -> FakeResponse:
        assert timeout == 30
        assert request.headers["User-agent"].startswith("san-antonio-311-pipeline")
        query = parse_qs(urlparse(request.full_url).query)
        offset = int(query["resultOffset"][0])
        return FakeResponse(json.dumps({"features": pages.get(offset, [])}))

    return opener


@pytest.mark.parametrize("page_size", [0, 2_001])
def test_build_query_url_rejects_invalid_page_size(page_size: int) -> None:
    with pytest.raises(ValueError, match="page_size"):
        build_query_url(page_size)


def test_build_query_url_contains_pagination_and_ordering() -> None:
    query = parse_qs(urlparse(build_query_url(25, offset=50)).query)
    assert query["resultRecordCount"] == ["25"]
    assert query["resultOffset"] == ["50"]
    assert query["orderByFields"] == ["OBJECTID ASC"]


def test_fetch_features_flattens_nullable_geometry() -> None:
    item = feature(1)
    item["geometry"] = None
    records = fetch_features(1, opener=fake_opener_for_pages({0: [item]}))
    assert records[0]["LONGITUDE"] is None
    assert records[0]["LATITUDE"] is None


def test_fetch_features_paginates_to_requested_limit() -> None:
    pages = {0: [feature(1), feature(2)], 2: [feature(3)]}
    records = fetch_features(3, opener=fake_opener_for_pages(pages), page_size=2)
    assert [record["OBJECTID"] for record in records] == [1, 2, 3]


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"error": {"message": "Unavailable"}}, "Unavailable"),
        ({"not_features": []}, "features list"),
    ],
)
def test_fetch_features_rejects_api_errors(payload: dict[str, Any], message: str) -> None:
    def opener(request: Any, timeout: int) -> FakeResponse:
        return FakeResponse(json.dumps(payload))

    with pytest.raises((RuntimeError, TypeError), match=message):
        fetch_features(1, opener=opener)


def test_fetch_features_rejects_missing_required_fields() -> None:
    invalid = feature(1)
    del invalid["attributes"]["SRNUMBER"]
    with pytest.raises(ValueError, match="SRNUMBER"):
        fetch_features(1, opener=fake_opener_for_pages({0: [invalid]}))


def test_fetch_features_rejects_non_numeric_coordinates() -> None:
    invalid = feature(1)
    invalid["geometry"]["x"] = "not-a-number"
    with pytest.raises(TypeError, match="longitude"):
        fetch_features(1, opener=fake_opener_for_pages({0: [invalid]}))


def test_write_jsonl_replaces_existing_file(tmp_path: Path) -> None:
    output = tmp_path / "raw" / "requests.jsonl"
    output.parent.mkdir()
    output.write_text("old data\n", encoding="utf-8")
    write_jsonl([{"OBJECTID": 1}, {"OBJECTID": 2}], output)
    assert output.read_text(encoding="utf-8").splitlines() == [
        '{"OBJECTID": 1}',
        '{"OBJECTID": 2}',
    ]
    assert not list(output.parent.glob("*.tmp"))


def test_default_output_path_is_timestamped() -> None:
    now = datetime(2026, 9, 14, 20, 30, tzinfo=UTC)
    assert default_output_path(now) == Path(
        "data/raw/extracted_at=2026-09-14T20-30-00.000000Z/service_requests.jsonl"
    )


def test_write_metadata_records_provenance(tmp_path: Path) -> None:
    output = tmp_path / "service_requests.jsonl"
    extracted_at = datetime(2026, 9, 14, tzinfo=UTC)
    metadata_path = write_metadata(output, 5, 3, extracted_at)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["requested_records"] == 5
    assert metadata["actual_records"] == 3
    assert metadata["source_url"].startswith("https://services.arcgis.com/")


def test_parse_args_rejects_non_positive_limit() -> None:
    with pytest.raises(SystemExit):
        parse_args(["--limit", "0"])


def test_main_runs_end_to_end_without_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "snapshot" / "requests.jsonl"
    monkeypatch.setattr(
        "san_antonio_311.ingest.fetch_features",
        lambda limit, page_size: [
            {
                "SRNUMBER": "102000000001",
                "STATUS": "OPEN",
                "CREATE_DATE": 1_700_000_000_000,
                "OBJECTID": 1,
            }
        ],
    )
    assert main(["--limit", "1", "--output", str(output)]) == 0
    assert output.exists()
    assert output.with_name("metadata.json").exists()
    assert "Wrote 1 records" in capsys.readouterr().out
