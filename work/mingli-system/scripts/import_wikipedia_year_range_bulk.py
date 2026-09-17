from __future__ import annotations

import argparse
import json
import sqlite3
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.error import HTTPError

from calculate_chart_snapshots import run as calculate_snapshots
from evaluate_quality_rules import run as evaluate_rules
from import_wikidata_entities import run as import_wikidata_entities
from import_wikipedia_birth_year import category_members, wikidata_qids_for_pages, write_qids
from init_database import DEFAULT_DB
from validate_database import validate


ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "cache"
SOURCE_ID = "OPEN_WIKIDATA_CC0"
WIKIDATA_QUERY_API = "https://query.wikidata.org/sparql"


def completed_years(db_path: Path, batch_prefix: str) -> set[int]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT batch_id
            FROM import_batches
            WHERE batch_id LIKE ?
              AND status = 'finished'
            """,
            (f"{batch_prefix}%",),
        ).fetchall()
    finally:
        conn.close()

    years: set[int] = set()
    for (batch_id,) in rows:
        suffix = batch_id.removeprefix(batch_prefix)
        if suffix.isdigit():
            years.add(int(suffix))
    return years


def fetch_year(year: int, limit: int, reuse_cache: bool) -> dict[str, Any]:
    qids_path = CACHE / f"wikipedia_birth_year_{year}_qids.txt"
    if reuse_cache and qids_path.exists():
        qids = [line.strip() for line in qids_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if qids:
            return {"year": year, "unique_qids": len(qids), "qids": qids, "cache_hit": True}

    members = category_members(year, limit)
    page_ids = [int(item["pageid"]) for item in members if "pageid" in item]
    qids = wikidata_qids_for_pages(page_ids)
    write_qids(qids, qids_path)
    return {
        "year": year,
        "category_members": len(members),
        "page_ids": len(page_ids),
        "unique_qids": len(qids),
        "qids": qids,
        "cache_hit": False,
    }


def fetch_wikidata_year(year: int, limit: int, reuse_cache: bool) -> dict[str, Any]:
    qids_path = CACHE / f"wikidata_birth_year_{year}_qids.txt"
    if reuse_cache and qids_path.exists():
        qids = [line.strip() for line in qids_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if qids:
            return {"year": year, "unique_qids": len(qids), "qids": qids, "cache_hit": True}

    query = f"""
    SELECT DISTINCT ?person WHERE {{
      ?person wdt:P569 ?dob.
      hint:Prior hint:rangeSafe true.
      FILTER(?dob >= \"{year:04d}-01-01T00:00:00Z\"^^xsd:dateTime &&
             ?dob < \"{year + 1:04d}-01-01T00:00:00Z\"^^xsd:dateTime)
      ?person wdt:P31 wd:Q5.
    }}
    LIMIT {limit}
    """
    url = f"{WIKIDATA_QUERY_API}?{urllib.parse.urlencode({'query': query, 'format': 'json'})}"
    last_error: Exception | None = None
    for attempt in range(1, 6):
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/sparql-results+json",
                "User-Agent": "MingliValidationBulk/0.1 (local research; contact: local)",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))
            qids = sorted(
                {
                    binding["person"]["value"].rsplit("/", 1)[-1]
                    for binding in payload.get("results", {}).get("bindings", [])
                    if binding.get("person", {}).get("value")
                }
            )
            write_qids(qids, qids_path)
            return {"year": year, "unique_qids": len(qids), "qids": qids, "cache_hit": False}
        except HTTPError as exc:
            last_error = exc
            if exc.code not in {429, 500, 502, 503, 504}:
                break
        except Exception as exc:
            last_error = exc
        if attempt < 5:
            time.sleep(min(30, attempt * 5))
    raise RuntimeError(f"Wikidata Query Service failed for year {year}") from last_error


def record_year_status(
    db_path: Path,
    batch_prefix: str,
    year: int,
    status: str,
    record_count: int,
    notes: str,
) -> None:
    batch_type = "wikidata_birth_year" if batch_prefix.startswith("IMPORT_WIKIDATA_") else "wikipedia_birth_year"
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
                f"{batch_prefix}{year}",
                SOURCE_ID,
                batch_type,
                status,
                record_count,
                notes[:1000],
            ),
        )
        conn.commit()
    finally:
        conn.close()


def chunks(values: list[int], size: int) -> list[list[int]]:
    return [values[index:index + size] for index in range(0, len(values), size)]


def run(
    db_path: Path,
    start_year: int,
    end_year: int,
    limit: int,
    workers: int,
    years_per_import: int,
    reuse_cache: bool,
    refresh: bool,
    fetch_source: str,
) -> dict[str, Any]:
    if start_year > end_year:
        raise ValueError("start_year must not be greater than end_year")
    if workers < 1 or years_per_import < 1 or limit < 1:
        raise ValueError("workers, years_per_import, and limit must be positive")

    batch_prefix = (
        "IMPORT_WIKIDATA_BIRTH_YEAR_" if fetch_source == "wikidata" else "IMPORT_WIKIPEDIA_BIRTH_YEAR_"
    )
    fetch_function = fetch_wikidata_year if fetch_source == "wikidata" else fetch_year
    already_completed = set() if refresh else completed_years(db_path, batch_prefix)
    requested_years = list(range(start_year, end_year + 1))
    pending_years = [year for year in requested_years if year not in already_completed]
    skipped_years = sorted(set(requested_years) - set(pending_years))
    fetched: dict[int, dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []

    print(
        json.dumps(
            {
                "status": "starting_bulk_fetch",
                "pending_years": len(pending_years),
                "skipped_years": len(skipped_years),
                "workers": workers,
                "fetch_source": fetch_source,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(fetch_function, year, limit, reuse_cache): year for year in pending_years}
        for future in as_completed(futures):
            year = futures[future]
            try:
                result = future.result()
                fetched[year] = result
                print(
                    json.dumps(
                        {
                            "status": "fetched_year",
                            "year": year,
                            "unique_qids": result["unique_qids"],
                            "cache_hit": result["cache_hit"],
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
            except Exception as exc:
                error = {"year": year, "stage": "fetch", "error": str(exc)}
                errors.append(error)
                record_year_status(db_path, batch_prefix, year, "failed", 0, str(exc))
                print(json.dumps({"status": "failed_year", **error}, ensure_ascii=False), flush=True)

    imported_chunks = 0
    imported_records = 0
    fetched_years = sorted(fetched)
    for year_chunk in chunks(fetched_years, years_per_import):
        qids = sorted({qid for year in year_chunk for qid in fetched[year]["qids"]})
        qids_path = CACHE / f"{fetch_source}_birth_years_{year_chunk[0]}_{year_chunk[-1]}_qids.txt"
        write_qids(qids, qids_path)
        try:
            import_result = import_wikidata_entities(db_path, qids_path)
            imported_chunks += 1
            imported_records += int(import_result.get("imported_people", 0))
            for year in year_chunk:
                record_year_status(
                    db_path,
                    batch_prefix,
                    year,
                    "finished",
                    fetched[year]["unique_qids"],
                    f"Bulk year coverage imported with years {year_chunk[0]}-{year_chunk[-1]}.",
                )
            print(
                json.dumps(
                    {
                        "status": "imported_chunk",
                        "start_year": year_chunk[0],
                        "end_year": year_chunk[-1],
                        "unique_qids": len(qids),
                        "imported_people": import_result.get("imported_people"),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
        except Exception as exc:
            for year in year_chunk:
                errors.append({"year": year, "stage": "import", "error": str(exc)})
                record_year_status(db_path, batch_prefix, year, "failed", 0, str(exc))
            print(
                json.dumps(
                    {
                        "status": "failed_chunk",
                        "start_year": year_chunk[0],
                        "end_year": year_chunk[-1],
                        "error": str(exc),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

    chart_result = calculate_snapshots(db_path)
    eval_result = evaluate_rules(db_path)
    validation = validate(db_path)
    return {
        "start_year": start_year,
        "end_year": end_year,
        "limit": limit,
        "workers": workers,
        "fetch_source": fetch_source,
        "requested_years": len(requested_years),
        "skipped_years": len(skipped_years),
        "fetched_years": len(fetched),
        "failed_records": len(errors),
        "failed_years": sorted({error["year"] for error in errors}),
        "imported_chunks": imported_chunks,
        "imported_records": imported_records,
        "chart_snapshots": chart_result,
        "rule_evaluation": eval_result,
        "validation": validation,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Bulk import Wikipedia birth-year categories with concurrent fetches.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--start-year", type=int, required=True)
    parser.add_argument("--end-year", type=int, required=True)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--years-per-import", type=int, default=25)
    parser.add_argument("--reuse-cache", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--fetch-source", choices=("wikipedia", "wikidata"), default="wikipedia")
    args = parser.parse_args()
    result = run(
        args.db,
        args.start_year,
        args.end_year,
        args.limit,
        args.workers,
        args.years_per_import,
        args.reuse_cache,
        args.refresh,
        args.fetch_source,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["validation"]["ok"] and not result["failed_years"] else 1)


if __name__ == "__main__":
    main()
