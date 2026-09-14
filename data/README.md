# Data directories

- `raw/` contains source data exactly as received.
- `processed/` contains cleaned or transformed data.

Dataset files are local working artifacts and should not be committed unless a
small fixture is intentionally added for testing.

The initial source is the City of San Antonio's public `311 Open Service Calls`
ArcGIS layer. It contains current open requests and requests closed in the last
seven days rather than a complete historical record.
