from __future__ import annotations

import argparse
import json
import sqlite3
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "mingli_validation.db"
DEFAULT_QUERY = ROOT / "pipeline" / "wikidata_public_people_seed.rq"
ENDPOINT = "https://query.wikidata.org/sparql"
SOURCE_ID = "OPEN_WIKIDATA_CC0"


def dump(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


def fetch_sparql(query: str, timeout: int = 60, retries: int = 3) -> dict[str, Any]:
    params = urllib.parse.urlencode({"query": query, "format": "json"}).encode("utf-8")
    request = urllib.request.Request(
        ENDPOINT,
        data=params,
        headers={
            "Accept": "application/sparql-results+json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "MingliValidationSeed/0.1 (local research; contact: local)",
        },
        method="POST",
    )
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # Wikidata occasionally returns 5xx under load.
            last_error = exc
            if attempt < retries:
                time.sleep(2 * attempt)
    raise RuntimeError(f"SPARQL request failed after {retries} attempts") from last_error


def binding_value(binding: dict[str, Any], key: str) -> str | None:
    value = binding.get(key)
    if not value:
        return None
    return value.get("value")


def qid_from_uri(uri: str) -> str:
    return uri.rstrip("/").split("/")[-1]


def normalize_date(value: str | None) -> str | None:
    if not value:
        return None
    return value.replace("T00:00:00Z", "")


def date_precision(value: str | None) -> str:
    if not value:
        return "unknown"
    clean = normalize_date(value) or ""
    if len(clean) >= 10 and clean[4] == "-" and clean[7] == "-":
        return "day"
    if len(clean) >= 7 and clean[4] == "-":
        return "month"
    if len(clean) >= 4:
        return "year"
    return "unknown"


def merge_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    people: dict[str, dict[str, Any]] = {}
    occupations: dict[str, set[str]] = defaultdict(set)
    countries: dict[str, set[str]] = defaultdict(set)
    sources: dict[str, set[str]] = defaultdict(set)

    for row in rows:
        person_uri = binding_value(row, "person")
        if not person_uri:
            continue
        qid = qid_from_uri(person_uri)
        people.setdefault(
            qid,
            {
                "qid": qid,
                "person_uri": person_uri,
                "name": binding_value(row, "personLabel") or qid,
                "dob": normalize_date(binding_value(row, "dob")),
                "dod": normalize_date(binding_value(row, "dod")),
                "birth_place": binding_value(row, "birthPlaceLabel"),
            },
        )
        if binding_value(row, "occupationLabel"):
            occupations[qid].add(binding_value(row, "occupationLabel") or "")
        if binding_value(row, "countryLabel"):
            countries[qid].add(binding_value(row, "countryLabel") or "")
        sources[qid].add(SOURCE_ID)

    for qid, person in people.items():
        person["occupations"] = sorted(value for value in occupations[qid] if value)
        person["countries"] = sorted(value for value in countries[qid] if value)
        person["source_ids"] = sorted(sources[qid])
    return people


def quality_level(person: dict[str, Any]) -> str:
    if person.get("dob") and person.get("birth_place"):
        return "L2"
    if person.get("dob"):
        return "L1"
    return "L0"


def insert_people(conn: sqlite3.Connection, people: dict[str, dict[str, Any]], batch_id: str) -> int:
    count = 0
    for qid, person in people.items():
        public_person_id = f"WD_{qid}"
        conn.execute(
            """
            INSERT OR REPLACE INTO public_persons (
              public_person_id, wikidata_qid, external_ids_json, primary_name,
              aliases_json, language_labels_json, is_living, occupations_json,
              fields_json, countries_json, privacy_class, source_ids_json,
              quality_level, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                public_person_id,
                qid,
                dump({"wikidata_uri": person["person_uri"]}),
                person["name"],
                dump([]),
                dump({"zh_or_en": person["name"]}),
                0 if person.get("dod") else None,
                dump(person.get("occupations", [])),
                dump([]),
                dump(person.get("countries", [])),
                "public_figure",
                dump(person.get("source_ids", [SOURCE_ID])),
                quality_level(person),
            ),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO birth_facts (
              birth_fact_id, subject_type, subject_id, raw_birth_text,
              date_standard, date_precision, calendar_type, time_text,
              time_precision, place_raw, place_standard_json, source_url,
              source_id, confidence, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                f"BF_WD_{qid}",
                "public_person",
                public_person_id,
                person.get("dob"),
                person.get("dob"),
                date_precision(person.get("dob")),
                "solar",
                None,
                "unknown",
                person.get("birth_place"),
                dump({"raw": person.get("birth_place")}),
                person["person_uri"],
                SOURCE_ID,
                "medium",
            ),
        )
        count += 1

    conn.execute(
        """
        INSERT OR REPLACE INTO import_batches (
          batch_id, source_id, batch_type, status, record_count, finished_at, notes
        ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
        """,
        (
            batch_id,
            SOURCE_ID,
            "wikidata_public_people_seed",
            "finished",
            count,
            "Initial seed import from Wikidata SPARQL.",
        ),
    )
    return count


def apply_limit(query: str, limit: int | None) -> str:
    if not limit:
        return query
    lines = query.splitlines()
    replaced = False
    for index, line in enumerate(lines):
        if line.strip().upper().startswith("LIMIT "):
            lines[index] = f"LIMIT {limit}"
            replaced = True
            break
    if not replaced:
        lines.append(f"LIMIT {limit}")
    return "\n".join(lines)


def run(db_path: Path, query_path: Path, limit: int | None) -> dict[str, Any]:
    query = apply_limit(query_path.read_text(encoding="utf-8"), limit)
    started = int(time.time())
    batch_id = f"IMPORT_WIKIDATA_SEED_{started}"
    payload = fetch_sparql(query)
    rows = payload.get("results", {}).get("bindings", [])
    people = merge_rows(rows)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            """
            INSERT OR REPLACE INTO import_batches (
              batch_id, source_id, batch_type, status, record_count, notes
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (batch_id, SOURCE_ID, "wikidata_public_people_seed", "running", 0, "Seed import started."),
        )
        count = insert_people(conn, people, batch_id)
        conn.commit()
    finally:
        conn.close()

    return {
        "batch_id": batch_id,
        "raw_rows": len(rows),
        "unique_people": count,
        "db": str(db_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a seed batch of public people from Wikidata.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--query", type=Path, default=DEFAULT_QUERY)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    print(json.dumps(run(args.db, args.query, args.limit), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
