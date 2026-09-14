# San Antonio 311 Pipeline

A data engineering portfolio project for ingesting, validating, and analyzing City of San Antonio 311 service-request data.

## Data source

The first ingestion stage reads the City of San Antonio's public
[311 Open Service Calls](https://services.arcgis.com/g1fRTDLeMgspWrYp/arcgis/rest/services/311_Open_Service_Calls/FeatureServer/0)
ArcGIS Feature Service. The source is a daily view of open cases and cases closed
within the last seven days; it is not a complete historical archive.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
```

## Download a sample

```bash
sa311-ingest --limit 100
```

The command writes newline-delimited JSON to
`data/raw/service_requests.jsonl`. Raw data files are intentionally ignored by
Git. Use `--output PATH` to choose another destination. A single request is
limited to 2,000 records, matching the service's advertised response limit.

## Project structure

```text
src/san_antonio_311/  Python package
tests/                Automated tests
data/raw/             Unmodified source data (not committed)
data/processed/       Cleaned and transformed data (not committed)
```
