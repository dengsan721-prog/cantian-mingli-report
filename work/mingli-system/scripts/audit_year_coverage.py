from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

from init_database import DEFAULT_DB


def audit(db_path: Path, start_year: int, end_year: int) -> dict[str, Any]:
    if start_year > end_year:
        raise ValueError("start_year must not be greater than end_year")

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT CAST(substr(date_standard, 1, 4) AS INTEGER) AS birth_year,
                   COUNT(*) AS fact_count
            FROM birth_facts
            WHERE subject_type = 'public_person'
              AND date_standard IS NOT NULL
            GROUP BY birth_year
            """
        ).fetchall()
        marker_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM import_batches
            WHERE batch_id LIKE 'IMPORT_WIKIDATA_BIRTH_YEAR_%'
              AND status = 'finished'
            """
        ).fetchone()[0]
    finally:
        conn.close()

    counts = dict(rows)
    requested_years = list(range(start_year, end_year + 1))
    missing_years = [year for year in requested_years if counts.get(year, 0) == 0]
    covered_counts = [counts.get(year, 0) for year in requested_years]
    return {
        "database": str(db_path),
        "start_year": start_year,
        "end_year": end_year,
        "requested_years": len(requested_years),
        "covered_years": len(requested_years) - len(missing_years),
        "missing_years": missing_years,
        "min_records_per_year": min(covered_counts),
        "max_records_per_year": max(covered_counts),
        "wikidata_year_markers": marker_count,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit continuous public birth-year coverage.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--start-year", type=int, required=True)
    parser.add_argument("--end-year", type=int, required=True)
    args = parser.parse_args()
    result = audit(args.db, args.start_year, args.end_year)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if not result["missing_years"] else 1)


if __name__ == "__main__":
    main()
