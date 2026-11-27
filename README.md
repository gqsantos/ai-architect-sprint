# Employee and PTO Data Pipeline

## Purpose and Grain

This project demonstrates a small raw-to-modeled pipeline for employee and paid-time-off (PTO) data. DuckDB stores the local source and analytical tables, pandas performs row-level cleanup, and Pydantic v2 validates each cleaned record.

The target tables have explicit grains:

- `EMPLOYEE_CLEAN`: one row per employee (`id`).
- `PTO_CLEAN`: one row per PTO request, keyed by (`employee_id`, `pto_type`, `start_date`, `end_date`).

Employee and PTO records are validated and modeled independently; the pipeline does not join them, avoiding many-to-many row multiplication.

## Data Quality and Handling

The generated raw tables contain exact duplicate rows, nulls, whitespace and inconsistent casing, malformed IDs, invalid dates, reversed PTO date ranges, and a non-numeric approver ID.

The pipeline trims text; title-cases names, addresses, cities, and PTO types; lowercases email and status; uppercases province and postal code; parses dates; and converts IDs to integers. Pydantic then enforces positive IDs, non-empty required strings, valid email format, real dates, and PTO end dates on or after start dates.

- Exact duplicate raw rows are removed from the deduplicated set and written to quarantine with a duplicate reason.
- Rows that fail parsing or model validation are quarantined with the original row and validation failure reason.
- If distinct valid rows conflict at a target table's grain, all rows for that key are quarantined rather than choosing an arbitrary winner.
- Valid, non-conflicting rows populate the clean tables. The reconciliation check requires modeled rows plus quarantined rows to equal the raw row count for each source table.

Quarantine is stored in DuckDB as `quarantine` (`source_table`, `original_row`, `failure_reason`) and exported to `data/output/quarantine.csv`. The clean tables are exported as both CSV and Parquet.

## Run

From the repository root, initialize or recreate the sample database:

```bash
uv run python src/db_setup.py
```

Then run the cleaning and modeling pipeline:

```bash
uv run python src/pipeline.py
```

The default database is `data/exercise.duckdb`. The pipeline accepts an alternate existing database path through `DUCKDB_PATH`, for example:

```bash
DUCKDB_PATH=/path/to/exercise.duckdb uv run python src/pipeline.py
```

Outputs are written to `data/output/`: `EMPLOYEE_CLEAN.csv`, `EMPLOYEE_CLEAN.parquet`, `PTO_CLEAN.csv`, `PTO_CLEAN.parquet`, and `quarantine.csv`. The pipeline prints raw, deduplicated, valid, quarantined, and modeled counts with duplicate, validation, and grain-conflict quarantine breakdowns.

## Production Hardening

- Add orchestration with dependency management, retries, run history, alerting, and failure recovery.
- Add incremental processing with durable source watermarks, late-arriving-data handling, and idempotent upserts.
- Add automated unit and integration tests for cleaning, Pydantic failures, duplicate and grain handling, exports, reconciliation, and reruns.
- Add structured logs and metrics for row counts, quarantine reasons, freshness, and schema drift.