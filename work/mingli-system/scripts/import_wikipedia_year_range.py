from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from calculate_chart_snapshots import run as calculate_snapshots
from evaluate_quality_rules import run as evaluate_rules
from import_wikipedia_birth_year import run as import_birth_year
from init_database import DEFAULT_DB
from validate_database import validate


ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "cache"


def record_failed_batch(db_path: Path, year: int, error: Exception) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO import_batches (
              batch_id, source_id, batch_type, status, record_count,
              finished_at, notes
            ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
            """,
            (
                f"IMPORT_WIKIPEDIA_BIRTH_YEAR_{year}_FAILED",
                "OPEN_WIKIDATA_CC0",
                "wikipedia_birth_year",
                "failed",
                0,
                str(error)[:1000],
            ),
        )
        conn.commit()
    finally:
        conn.close()


def run(db_path: Path, start_year: int, end_year: int, limit: int, pause_seconds: float, continue_on_error: bool) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for year in range(start_year, end_year + 1):
        qids_path = CACHE / f"wikipedia_birth_year_{year}_qids.txt"
        try:
            result = import_birth_year(db_path, year, limit, qids_path)
            results.append(result)
        except Exception as exc:
            record_failed_batch(db_path, year, exc)
            errors.append({"year": year, "error": str(exc)})
            if not continue_on_error:
                break
        if pause_seconds:
            time.sleep(pause_seconds)

    chart_result = calculate_snapshots(db_path)
    eval_result = evaluate_rules(db_path)
    validation = validate(db_path)
    return {
        "start_year": start_year,
        "end_year": end_year,
        "limit": limit,
        "successful_years": len(results),
        "failed_years": len(errors),
        "results": results,
        "errors": errors,
        "chart_snapshots": chart_result,
        "rule_evaluation": eval_result,
        "validation": validation,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a throttled range of Wikipedia birth-year public people.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--start-year", type=int, required=True)
    parser.add_argument("--end-year", type=int, required=True)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--pause-seconds", type=float, default=8)
    parser.add_argument("--stop-on-error", action="store_true")
    args = parser.parse_args()
    result = run(
        args.db,
        args.start_year,
        args.end_year,
        args.limit,
        args.pause_seconds,
        continue_on_error=not args.stop_on_error,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["validation"]["ok"] else 1)


if __name__ == "__main__":
    main()

