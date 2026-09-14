# Data directories

- `raw/` is a landing zone for timestamped, lightly normalized source snapshots.
- `processed/` contains cleaned or transformed data.

Dataset files are local working artifacts and should not be committed unless a
small fixture is intentionally added for testing.

The initial source is the City of San Antonio's public `311 Open Service Calls`
ArcGIS layer. It contains current open requests and requests closed in the last
seven days rather than a complete historical record. Each extraction directory
contains JSONL records plus a `metadata.json` provenance file. Source attributes
are preserved, but ArcGIS geometry is flattened to longitude and latitude.
