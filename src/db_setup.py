from pathlib import Path

import duckdb


DATABASE_PATH = Path(__file__).resolve().parents[1] / "data" / "exercise.duckdb"

EMPLOYEE_ROWS = [
	("1001", "Maya", "Chen", "maya.chen@example.com", "555-0101", "1988-04-12", "14 Oak Street", "Portland", "OR", "97201"),
	("1002", "Liam", "Patel", "liam.patel@example.com", "555-0102", "1991-09-03", "82 Pine Avenue", "Salem", "OR", "97301"),
	("1003", "Sofia", "Garcia", "sofia.garcia@example.com", "555-0103", "1985-12-21", "7 Cedar Road", "Eugene", "OR", "97401"),
	("1004", "Noah", "Williams", "noah.williams@example.com", "555-0104", "1994-06-17", "203 Maple Lane", "Bend", "OR", "97701"),
	("1005", "Ava", "Johnson", "ava.johnson@example.com", "555-0105", "1990-02-28", "19 Birch Court", "Portland", "OR", "97205"),
	("1006", "Ethan", "Kim", "ethan.kim@example.com", "555-0106", "1982-11-09", "55 River Drive", "Hillsboro", "OR", "97123"),
	("1007", "Isabella", "Brown", "isabella.brown@example.com", "555-0107", "1997-03-14", "6 Spruce Way", "Gresham", "OR", "97030"),
	("1008", "Oliver", "Davis", "oliver.davis@example.com", "555-0108", "1989-07-26", "31 Elm Street", "Corvallis", "OR", "97330"),
	("1009", "Amelia", "Wilson", "amelia.wilson@example.com", "555-0109", "1993-10-05", "90 Ash Boulevard", "Medford", "OR", "97501"),
	("1010", "Lucas", "Martinez", "lucas.martinez@example.com", "555-0110", "1986-01-19", "12 Willow Place", "Portland", "OR", "97209"),
	("1011", " Mia ", "THOMAS", "Mia.Thomas@Example.com ", " 555-0111 ", "1992-08-30", " 4 Fir Terrace ", " portland ", "or", "97211"),
	("1012", "James", "Taylor", None, "555-0112", "1980-05-22", "73 Lake Street", "Ashland", "OR", "97520"),
	("1013", "Charlotte", "Anderson", "charlotte.anderson@example.com", None, "1995-13-40", "8 Summit Road", "Beaverton", "OR", "97005"),
	("N/A", "Benjamin", "Moore", "benjamin.moore@example.com", "555-0114", "1987-02-16", "29 Park Avenue", "Tigard", "OR", "97223"),
	("10O5", "Harper", "Jackson", "harper.jackson@example.com", "555-0115", "1998-04-07", "44 Garden Street", "Lake Oswego", "OR", "97034"),
	("1001", "Maya", "Chen", "maya.chen@example.com", "555-0101", "1988-04-12", "14 Oak Street", "Portland", "OR", "97201"),
]

PTO_ROWS = [
	("1001", "Vacation", "2026-01-12", "2026-01-16", "approved", "2001"),
	("1002", "Sick", "2026-02-03", "2026-02-04", "approved", "2002"),
	("1003", "Personal", "2026-03-20", "2026-03-20", "pending", "2001"),
	("1004", "Vacation", "2026-04-06", "2026-04-10", "approved", "2003"),
	("1005", "Parental", "2026-05-01", "2026-05-29", "pending", "2002"),
	("1006", "Sick", "2026-01-22", "2026-01-23", "denied", "2001"),
	("1007", "Vacation", "2026-06-15", "2026-06-19", "approved", "2003"),
	("1008", "Personal", "2026-07-02", "2026-07-02", "approved", "2002"),
	("1009", "Vacation", "2026-08-10", "2026-08-14", "pending", "2001"),
	("1010", "Sick", "2026-09-08", "2026-09-08", "approved", "2003"),
	("1011", " vacation ", "2026-10-19", "2026-10-23", " APPROVED ", " 2002 "),
	("1012", "sICK", "2026-11-02", "2026-11-03", "Pending", "2001"),
	("1013", "Personal", "2026-02-30", "2026-03-01", "approved", "2002"),
	("10O5", "Vacation", "2026-12-15", "2026-12-12", "approved", "two thousand"),
	(None, "Bereavement", "not-a-date", "2026-12-04", " pending ", None),
	("1001", "Vacation", "2026-01-12", "2026-01-16", "approved", "2001"),
]


def main() -> None:
	DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
	connection = duckdb.connect(str(DATABASE_PATH))
	try:
		connection.execute("DROP TABLE IF EXISTS employee")
		connection.execute("DROP TABLE IF EXISTS pto")
		connection.execute(
			"""
			CREATE TABLE employee (
				id VARCHAR,
				first_name VARCHAR,
				last_name VARCHAR,
				email VARCHAR,
				phone VARCHAR,
				birthdate VARCHAR,
				street_address VARCHAR,
				city VARCHAR,
				province VARCHAR,
				postal_code VARCHAR
			)
			"""
		)
		connection.execute(
			"""
			CREATE TABLE pto (
				employee_id VARCHAR,
				pto_type VARCHAR,
				start_date VARCHAR,
				end_date VARCHAR,
				status VARCHAR,
				approver_id VARCHAR
			)
			"""
		)
		connection.executemany(
			"INSERT INTO employee VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
			EMPLOYEE_ROWS,
		)
		connection.executemany(
			"INSERT INTO pto VALUES (?, ?, ?, ?, ?, ?)",
			PTO_ROWS,
		)

		for table_name in ("employee", "pto"):
			row_count = connection.execute(
				f"SELECT COUNT(*) FROM {table_name}"
			).fetchone()[0]
			print(f"{table_name} raw row count: {row_count}")
	finally:
		connection.close()


if __name__ == "__main__":
	main()
