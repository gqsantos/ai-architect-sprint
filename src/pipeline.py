import json
import os
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Callable, TypeVar

import duckdb
import pandas as pd
from pydantic import BaseModel, ValidationError

if __package__:
	from .models import EmployeeRecord, PTORecord, QuarantinedRecord
else:
	from models import EmployeeRecord, PTORecord, QuarantinedRecord


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "data" / "exercise.duckdb"
OUTPUT_DIRECTORY = PROJECT_ROOT / "data" / "output"

EMPLOYEE_COLUMNS = (
	"id",
	"first_name",
	"last_name",
	"email",
	"phone",
	"birthdate",
	"street_address",
	"city",
	"province",
	"postal_code",
)
PTO_COLUMNS = (
	"employee_id",
	"pto_type",
	"start_date",
	"end_date",
	"status",
	"approver_id",
)

MODEL = TypeVar("MODEL", bound=BaseModel)


def _database_path() -> Path:
	configured_path = os.environ.get("DUCKDB_PATH")
	if configured_path:
		return Path(configured_path).expanduser()
	return DEFAULT_DATABASE_PATH


def _is_missing(value: Any) -> bool:
	if value is None:
		return True
	return bool(pd.isna(value))


def _raw_value(value: Any) -> Any:
	if _is_missing(value):
		return None
	if isinstance(value, pd.Timestamp):
		return value.isoformat()
	if hasattr(value, "item"):
		return value.item()
	return value


def _clean_text(value: Any, casing: str = "preserve") -> str | None:
	if _is_missing(value):
		return None
	text = str(value).strip()
	if casing == "lower":
		return text.lower()
	if casing == "upper":
		return text.upper()
	if casing == "title":
		return text.title()
	return text


def _clean_positive_integer(value: Any) -> int | str | None:
	text = _clean_text(value)
	if text is None or text == "":
		return text
	try:
		return int(text)
	except ValueError:
		return text


def _clean_date(value: Any) -> date | None:
	text = _clean_text(value)
	if not text:
		return None
	parsed = pd.to_datetime(text, errors="coerce")
	if pd.isna(parsed):
		return None
	return parsed.date()


def _normalize_employee(row: dict[str, Any]) -> dict[str, Any]:
	return {
		"id": _clean_positive_integer(row["id"]),
		"first_name": _clean_text(row["first_name"], "title"),
		"last_name": _clean_text(row["last_name"], "title"),
		"email": _clean_text(row["email"], "lower"),
		"phone": _clean_text(row["phone"]),
		"birthdate": _clean_date(row["birthdate"]),
		"street_address": _clean_text(row["street_address"], "title"),
		"city": _clean_text(row["city"], "title"),
		"province": _clean_text(row["province"], "upper"),
		"postal_code": _clean_text(row["postal_code"], "upper"),
	}


def _normalize_pto(row: dict[str, Any]) -> dict[str, Any]:
	return {
		"employee_id": _clean_positive_integer(row["employee_id"]),
		"pto_type": _clean_text(row["pto_type"], "title"),
		"start_date": _clean_date(row["start_date"]),
		"end_date": _clean_date(row["end_date"]),
		"status": _clean_text(row["status"], "lower"),
		"approver_id": _clean_positive_integer(row["approver_id"]),
	}


def _deduplicate(
	dataframe: pd.DataFrame,
	columns: tuple[str, ...],
	normalizer: Callable[[dict[str, Any]], dict[str, Any]],
	source_table: str,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
	rows = []
	for raw_row in dataframe.to_dict(orient="records"):
		original_row = {key: _raw_value(value) for key, value in raw_row.items()}
		fingerprint = json.dumps(original_row, sort_keys=True, ensure_ascii=True, default=str)
		rows.append(
			{
				**normalizer(original_row),
				"_original_row": original_row,
				"_raw_fingerprint": fingerprint,
			}
		)

	normalized = pd.DataFrame(
		rows,
		columns=[*columns, "_original_row", "_raw_fingerprint"],
		dtype=object,
	)
	duplicate_mask = normalized.duplicated(subset=["_raw_fingerprint"], keep="first")
	duplicate_quarantine = [
		_quarantine_entry(
			source_table,
			row["_original_row"],
			"exact duplicate row removed during deduplication",
		)
		for row in normalized.loc[duplicate_mask].to_dict(orient="records")
	]
	deduplicated = normalized.loc[~duplicate_mask].drop(columns="_raw_fingerprint")
	return deduplicated.reset_index(drop=True), duplicate_quarantine


def _format_validation_error(error: ValidationError) -> str:
	messages = []
	for item in error.errors():
		location = ".".join(str(part) for part in item["loc"]) or "record"
		messages.append(f"{location}: {item['msg']}")
	return "; ".join(messages)


def _quarantine_entry(source_table: str, original_row: dict[str, Any], reason: str) -> dict[str, Any]:
	quarantined = QuarantinedRecord(
		original_row=original_row,
		failure_reason=reason,
	)
	return {
		"source_table": source_table,
		"original_row": quarantined.original_row,
		"failure_reason": quarantined.failure_reason,
	}


def _validate_rows(
	source_table: str,
	deduplicated_rows: pd.DataFrame,
	columns: tuple[str, ...],
	model_type: type[MODEL],
) -> tuple[list[tuple[MODEL, dict[str, Any]]], list[dict[str, Any]]]:
	valid_rows: list[tuple[MODEL, dict[str, Any]]] = []
	quarantined_rows = []
	for cleaned_row in deduplicated_rows.to_dict(orient="records"):
		original_row = cleaned_row.pop("_original_row")
		model_input = {column: cleaned_row[column] for column in columns}
		try:
			valid_rows.append((model_type.model_validate(model_input), original_row))
		except ValidationError as error:
			quarantined_rows.append(
				_quarantine_entry(source_table, original_row, _format_validation_error(error))
			)
	return valid_rows, quarantined_rows


def _enforce_grain(
	valid_rows: list[tuple[MODEL, dict[str, Any]]],
	key_function: Callable[[MODEL], tuple[Any, ...]],
	source_table: str,
	grain_description: str,
) -> tuple[list[tuple[MODEL, dict[str, Any]]], list[dict[str, Any]]]:
	rows_by_key: dict[tuple[Any, ...], list[tuple[MODEL, dict[str, Any]]]] = defaultdict(list)
	for item in valid_rows:
		rows_by_key[key_function(item[0])].append(item)

	unique_rows = []
	quarantined_rows = []
	for same_key_rows in rows_by_key.values():
		if len(same_key_rows) == 1:
			unique_rows.extend(same_key_rows)
			continue
		for _, original_row in same_key_rows:
			quarantined_rows.append(
				_quarantine_entry(
					source_table,
					original_row,
					f"conflicting records share the {grain_description} grain",
				)
			)
	return unique_rows, quarantined_rows


def _insert_models(
	connection: duckdb.DuckDBPyConnection,
	table_name: str,
	columns: tuple[str, ...],
	rows: list[tuple[BaseModel, dict[str, Any]]],
) -> None:
	if not rows:
		return
	placeholders = ", ".join("?" for _ in columns)
	column_names = ", ".join(columns)
	values = [tuple(getattr(model, column) for column in columns) for model, _ in rows]
	connection.executemany(
		f"INSERT INTO {table_name} ({column_names}) VALUES ({placeholders})",
		values,
	)


def _create_modeled_tables(connection: duckdb.DuckDBPyConnection) -> None:
	connection.execute(
		"""
		CREATE OR REPLACE TABLE EMPLOYEE_CLEAN (
			id INTEGER NOT NULL,
			first_name VARCHAR NOT NULL,
			last_name VARCHAR NOT NULL,
			email VARCHAR NOT NULL,
			phone VARCHAR NOT NULL,
			birthdate DATE NOT NULL,
			street_address VARCHAR NOT NULL,
			city VARCHAR NOT NULL,
			province VARCHAR NOT NULL,
			postal_code VARCHAR NOT NULL,
			PRIMARY KEY (id)
		)
		"""
	)
	connection.execute(
		"""
		CREATE OR REPLACE TABLE PTO_CLEAN (
			employee_id INTEGER NOT NULL,
			pto_type VARCHAR NOT NULL,
			start_date DATE NOT NULL,
			end_date DATE NOT NULL,
			status VARCHAR NOT NULL,
			approver_id INTEGER NOT NULL,
			UNIQUE (employee_id, pto_type, start_date, end_date)
		)
		"""
	)
	connection.execute(
		"""
		CREATE OR REPLACE TABLE quarantine (
			source_table VARCHAR NOT NULL,
			original_row JSON NOT NULL,
			failure_reason VARCHAR NOT NULL
		)
		"""
	)


def _write_quarantine(
	connection: duckdb.DuckDBPyConnection,
	quarantined_rows: list[dict[str, Any]],
) -> None:
	if not quarantined_rows:
		return
	connection.executemany(
		"INSERT INTO quarantine VALUES (?, CAST(? AS JSON), ?)",
		[
			(
				row["source_table"],
				json.dumps(row["original_row"], ensure_ascii=True, default=str),
				row["failure_reason"],
			)
			for row in quarantined_rows
		],
	)


def _export_table(
	connection: duckdb.DuckDBPyConnection,
	table_name: str,
	output_directory: Path,
) -> int:
	dataframe = connection.execute(f"SELECT * FROM {table_name}").df()
	dataframe.to_csv(output_directory / f"{table_name}.csv", index=False)
	dataframe.to_parquet(output_directory / f"{table_name}.parquet", index=False)
	return len(dataframe)


def main() -> None:
	database_path = _database_path()
	database_path.parent.mkdir(parents=True, exist_ok=True)
	OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)

	connection = duckdb.connect(str(database_path))
	try:
		employee_raw = connection.execute("SELECT * FROM employee").df()
		pto_raw = connection.execute("SELECT * FROM pto").df()

		employee_deduplicated, employee_duplicate_quarantined = _deduplicate(
			employee_raw, EMPLOYEE_COLUMNS, _normalize_employee, "employee"
		)
		pto_deduplicated, pto_duplicate_quarantined = _deduplicate(
			pto_raw, PTO_COLUMNS, _normalize_pto, "pto"
		)

		employee_validated, employee_quarantined = _validate_rows(
			"employee", employee_deduplicated, EMPLOYEE_COLUMNS, EmployeeRecord
		)
		pto_validated, pto_quarantined = _validate_rows(
			"pto", pto_deduplicated, PTO_COLUMNS, PTORecord
		)

		employee_valid, employee_grain_quarantine = _enforce_grain(
			employee_validated,
			lambda row: (row.id,),
			"employee",
			"one-row-per-employee",
		)
		pto_valid, pto_grain_quarantine = _enforce_grain(
			pto_validated,
			lambda row: (row.employee_id, row.pto_type, row.start_date, row.end_date),
			"pto",
			"one-row-per-PTO-request",
		)
		all_quarantined = (
			employee_duplicate_quarantined
			+ pto_duplicate_quarantined
			+ employee_quarantined
			+ pto_quarantined
			+ employee_grain_quarantine
			+ pto_grain_quarantine
		)

		connection.execute("BEGIN TRANSACTION")
		try:
			_create_modeled_tables(connection)
			_insert_models(connection, "EMPLOYEE_CLEAN", EMPLOYEE_COLUMNS, employee_valid)
			_insert_models(connection, "PTO_CLEAN", PTO_COLUMNS, pto_valid)
			_write_quarantine(connection, all_quarantined)
			connection.execute("COMMIT")
		except Exception:
			connection.execute("ROLLBACK")
			raise

		employee_modeled_count = _export_table(connection, "EMPLOYEE_CLEAN", OUTPUT_DIRECTORY)
		pto_modeled_count = _export_table(connection, "PTO_CLEAN", OUTPUT_DIRECTORY)
		quarantine_dataframe = connection.execute(
			"SELECT source_table, original_row, failure_reason FROM quarantine"
		).df()
		quarantine_dataframe.to_csv(OUTPUT_DIRECTORY / "quarantine.csv", index=False)

		employee_quarantine_count = (
			len(employee_duplicate_quarantined)
			+ len(employee_quarantined)
			+ len(employee_grain_quarantine)
		)
		pto_quarantine_count = (
			len(pto_duplicate_quarantined)
			+ len(pto_quarantined)
			+ len(pto_grain_quarantine)
		)
		quarantine_table_count = connection.execute(
			"SELECT COUNT(*) FROM quarantine"
		).fetchone()[0]
		print("Reconciliation report (raw -> deduplicated -> valid -> quarantined -> modeled)")
		print(
			f"employee: raw={len(employee_raw)} -> deduplicated={len(employee_deduplicated)} "
			f"-> validation_valid={len(employee_validated)} "
			f"-> EMPLOYEE_CLEAN={employee_modeled_count}; "
			f"quarantined: duplicate={len(employee_duplicate_quarantined)}, "
			f"validation={len(employee_quarantined)}, "
			f"grain={len(employee_grain_quarantine)}, total={employee_quarantine_count}"
		)
		print(
			f"pto: raw={len(pto_raw)} -> deduplicated={len(pto_deduplicated)} "
			f"-> validation_valid={len(pto_validated)} "
			f"-> PTO_CLEAN={pto_modeled_count}; "
			f"quarantined: duplicate={len(pto_duplicate_quarantined)}, "
			f"validation={len(pto_quarantined)}, "
			f"grain={len(pto_grain_quarantine)}, total={pto_quarantine_count}"
		)
		print(f"quarantine table/CSV rows: {quarantine_table_count}")
		if len(employee_raw) != employee_modeled_count + employee_quarantine_count:
			raise RuntimeError("employee reconciliation failed: modeled plus quarantine != raw")
		if len(pto_raw) != pto_modeled_count + pto_quarantine_count:
			raise RuntimeError("pto reconciliation failed: modeled plus quarantine != raw")
	finally:
		connection.close()


if __name__ == "__main__":
	main()
