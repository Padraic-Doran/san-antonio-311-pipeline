# San Antonio 311 Pipeline

A data engineering portfolio project for ingesting, validating, and analyzing City of San Antonio 311 service-request data.

The project is being built in small, testable stages. It currently provides a
command-line extractor, schema checks, paginated downloads, timestamped local
snapshots, reusable exploratory helpers, and a Jupyter notebook.

## Current capabilities

- Queries the official public 311 feature layer without an API key.
- Paginates requests while ordering each current snapshot by `OBJECTID`.
- Preserves source attributes while flattening map geometry into `LONGITUDE`
  and `LATITUDE` fields.
- Writes atomically so an interrupted run does not leave a partial output file.
- Preserves earlier runs in timestamped directories and records provenance
  metadata beside every snapshot.
- Validates the ArcGIS response structure and required record fields.
- Keeps downloaded datasets out of Git while retaining the data directories.
- Provides reusable pandas helpers for dataset summaries, missing values,
  duplicate request numbers, date conversion, and category counts.
- Cleans landing snapshots into analysis-ready records with normalized text,
  UTC timestamps, lowercase column names, deterministic deduplication, and a
  quality report.
- Loads processed records into a reproducible PostgreSQL database and safely
  updates existing requests using `srnumber` as the primary key.

## Data source

The first ingestion stage reads the City of San Antonio's public
[311 Open Service Calls](https://services.arcgis.com/g1fRTDLeMgspWrYp/arcgis/rest/services/311_Open_Service_Calls/FeatureServer/0)
ArcGIS Feature Service. The source is a daily view of open cases and cases closed
within the last seven days; it is not a complete historical archive.

## Project status

| Stage | Status |
| --- | --- |
| Official API discovery | Complete |
| Validated, paginated ingestion | Complete |
| Timestamped snapshot storage | Complete |
| Exploratory notebook and helpers | Complete |
| Automated tests and GitHub Actions | Complete |
| Cleaning and transformation | Complete |
| PostgreSQL loading | Complete |
| Historical trend analysis | Planned |

## Development setup

Requirements: Python 3.11 or newer and Git.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install '.[dev,notebook]'
pytest
ruff check .
```

## Explore in Jupyter

If you prefer notebooks, start JupyterLab from the project folder:

```bash
source .venv/bin/activate
jupyter lab
```

Then open `notebooks/01_explore_311_data.ipynb` and run its cells from top to
bottom. The notebook reuses the functions in `ingest.py`, loads the result into
pandas, examines columns and missing values, summarizes categories and statuses,
and creates a simple chart. It is an exploration layer over the same reusable
pipeline code—not a separate implementation.

## Download a sample

```bash
sa311-ingest --limit 100
```

By default, each command creates a new timestamped landing-zone snapshot:

```text
data/raw/extracted_at=2026-09-14T20-30-00.000000Z/
├── service_requests.jsonl
└── metadata.json
```

The service limits an individual API page to 2,000 records. The command
automatically makes additional paginated requests when `--limit` is larger.
Downloaded files are intentionally ignored by Git.

Choose a different output file when needed:

```bash
sa311-ingest --limit 250 --output data/raw/sample_250.jsonl
```

Each line is one independent JSON object. A record includes identifiers and
descriptive fields such as `SRNUMBER`, `STATUS`, `CATEGORY`, `TITLE`, dates,
council district, and coordinates. ArcGIS date values are currently preserved
as Unix epoch milliseconds so the raw stage remains faithful to the source.

These landing-zone records are **lightly normalized**, not byte-for-byte copies
of the ArcGIS response: selected source attributes are retained while nested
geometry is flattened into `LONGITUDE` and `LATITUDE`. `metadata.json` records
the extraction time, source URL, and requested versus actual record counts.

## Transform a snapshot

Pass an ingested JSONL file to the transformation command:

```bash
sa311-transform \
  --input data/raw/extracted_at=TIMESTAMP/service_requests.jsonl
```

The default output mirrors the timestamp under `data/processed/` and adds a
quality report:

```text
data/processed/extracted_at=TIMESTAMP/
├── service_requests.jsonl
└── quality_report.json
```

The transformation trims text, replaces empty strings with missing values,
uppercases statuses, converts ArcGIS dates to UTC ISO-8601 values, changes column
names to lowercase, flags invalid coordinates, and keeps the most recently
updated row when a service-request number is duplicated. The landing snapshot is
left unchanged.

## Load PostgreSQL

Docker keeps the development database reproducible and isolated from other
projects. Start it from the repository root:

```bash
docker compose up -d postgres
export DATABASE_URL=postgresql://sa311:sa311_dev@localhost:5432/sa311
```

Load a processed snapshot:

```bash
sa311-load \
  --input data/processed/extracted_at=TIMESTAMP/service_requests.jsonl
```

The loader creates the `service_requests` table and indexes automatically. It
uses an upsert: a new `srnumber` is inserted, while an existing `srnumber` is
updated with the newest processed values. The entire load is one transaction,
so a failure rolls it back instead of partially updating the table.

Inspect the database with PostgreSQL's command-line client:

```bash
psql "$DATABASE_URL"
```

Example SQL queries:

```sql
SELECT status, count(*)
FROM service_requests
GROUP BY status
ORDER BY count(*) DESC;

SELECT category, count(*)
FROM service_requests
GROUP BY category
ORDER BY count(*) DESC
LIMIT 10;
```

Stop the container without deleting its saved database volume:

```bash
docker compose down
```

## Pipeline flow

```text
City of San Antonio ArcGIS Feature Service
                    |
                    v
       validate and flatten response
                    |
                    v
  timestamped landing snapshot + metadata
                    |
                    v
       validate, clean, and deduplicate
                    |
                    v
 processed JSONL snapshot + quality report
                    |
                    v
          PostgreSQL upsert by srnumber
```

## Python execution order

The smaller functions each perform one focused job, while `main()` coordinates
their order. `build_query_url()` is nested under `fetch_features()` because
building the URL is one step in the download operation.

```text
main()
├── parse_args()           Read command options
├── default_output_path()  Choose a timestamped destination when needed
├── fetch_features()      Download, paginate, validate, and flatten records
│   └── build_query_url()  Build each ArcGIS page URL
├── write_jsonl()         Save the records safely
└── write_metadata()      Save extraction provenance
```

The separate `sa311-transform` command follows the same coordinator pattern:

```text
main()
├── load_jsonl()            Load one landing snapshot
├── transform_records()     Clean, convert, flag, and deduplicate
├── write_processed_jsonl() Save analysis-ready records
└── write_quality_report()  Save row-level quality counts
```

`sa311-load` then coordinates the database stage:

```text
main()
├── load_processed_jsonl() Validate the processed file
├── ensure_schema()        Create the table and indexes if needed
└── upsert_records()       Insert new or update existing requests
```

When `sa311-ingest` starts, Python calls `main()`. Python then follows the
statements inside `main()` from top to bottom, temporarily entering each called
function and returning before continuing to the next statement.

## Project structure

```text
src/san_antonio_311/  Python package
src/san_antonio_311/sql/ PostgreSQL schema
tests/                Automated tests
notebooks/            Jupyter exploration and learning
data/raw/             Timestamped landing snapshots (not committed)
data/processed/       Cleaned and transformed data (not committed)
docker-compose.yml    Local PostgreSQL service
```

## Run quality checks

```bash
coverage run -m pytest
coverage report
ruff check .
```

The tests exercise pagination, schema and error handling, record transformation,
atomic JSONL writing, metadata, command entry points, exploratory helpers, SQL
generation, and PostgreSQL upserts without calling the live API. GitHub Actions
runs the same checks against a real PostgreSQL service on Python 3.11 and 3.14
after every push and pull request.

## Known limitation

The current city layer is a recent operational snapshot—not a historical
archive. Timestamped runs can build local history going forward, but they do not
recover requests that disappeared before collection began. Ordering by
`OBJECTID` is stable within a snapshot; the source can change between daily
refreshes.
