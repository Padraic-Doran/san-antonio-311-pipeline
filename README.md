# San Antonio 311 Pipeline

A data engineering portfolio project for ingesting, validating, and analyzing City of San Antonio 311 service-request data.

The project is being built in small, testable stages. The current stage provides
a command-line extractor that downloads a bounded snapshot from the city's
public ArcGIS service and stores it locally as JSON Lines.

## Current capabilities

- Queries the official public 311 feature layer without an API key.
- Selects a predictable sample by ordering records by `OBJECTID`.
- Preserves source attributes while flattening map geometry into `LONGITUDE`
  and `LATITUDE` fields.
- Writes atomically so an interrupted run does not leave a partial output file.
- Keeps downloaded datasets out of Git while retaining the data directories.
- Provides reusable pandas helpers for dataset summaries, missing values,
  duplicate request numbers, date conversion, and category counts.

## Data source

The first ingestion stage reads the City of San Antonio's public
[311 Open Service Calls](https://services.arcgis.com/g1fRTDLeMgspWrYp/arcgis/rest/services/311_Open_Service_Calls/FeatureServer/0)
ArcGIS Feature Service. The source is a daily view of open cases and cases closed
within the last seven days; it is not a complete historical archive.

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

The command writes newline-delimited JSON to
`data/raw/service_requests.jsonl`. Raw data files are intentionally ignored by
Git. Use `--output PATH` to choose another destination. A single request is
limited to 2,000 records, matching the service's advertised response limit.

Choose a different output file when needed:

```bash
sa311-ingest --limit 250 --output data/raw/sample_250.jsonl
```

Each line is one independent JSON object. A record includes identifiers and
descriptive fields such as `SRNUMBER`, `STATUS`, `CATEGORY`, `TITLE`, dates,
council district, and coordinates. ArcGIS date values are currently preserved
as Unix epoch milliseconds so the raw stage remains faithful to the source.

## Pipeline flow

```text
City of San Antonio ArcGIS Feature Service
                    |
                    v
       validate and flatten response
                    |
                    v
     data/raw/service_requests.jsonl
```

## Python execution order

The smaller functions each perform one focused job, while `main()` coordinates
their order. `build_query_url()` is nested under `fetch_features()` because
building the URL is one step in the download operation.

```text
main()
├── parse_args()          Read --limit and --output
├── fetch_features()     Download and flatten the records
│   └── build_query_url() Build the ArcGIS request URL
└── write_jsonl()        Save the records safely
```

When `sa311-ingest` starts, Python calls `main()`. Python then follows the
statements inside `main()` from top to bottom, temporarily entering each called
function and returning before continuing to the next statement.

## Project structure

```text
src/san_antonio_311/  Python package
tests/                Automated tests
notebooks/            Jupyter exploration and learning
data/raw/             Unmodified source data (not committed)
data/processed/       Cleaned and transformed data (not committed)
```

## Run quality checks

```bash
pytest
ruff check .
```

The tests exercise URL construction, the ArcGIS response transformation, JSONL
writing, exploratory analysis helpers, and package installation without calling
the live API.

## Known limitation

The current city layer is a recent operational snapshot—not a historical
archive. The next milestone is to locate an authoritative historical source or
begin storing dated snapshots, then add schema validation and incremental-load
behavior.
