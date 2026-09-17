from __future__ import annotations

import argparse
import json
import sqlite3
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from import_wikidata_entities import claim_item_ids, claim_values, fetch_entities
from init_database import DEFAULT_DB


ENRICHMENT_VERSION = "wikidata-birthplace-geo-v1"
CURSOR_KEY = f"{ENRICHMENT_VERSION}_cursor"
CLAIM_COORDINATE = "P625"
CLAIM_TIMEZONE = "P421"


def chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index:index + size] for index in range(0, len(values), size)]


def load_place_index(conn: sqlite3.Connection) -> dict[str, list[str]]:
    index: dict[str, list[str]] = defaultdict(list)
    for birth_fact_id, raw_json in conn.execute(
        "SELECT birth_fact_id, place_standard_json FROM birth_facts WHERE subject_type = 'public_person'"
    ):
        try:
            value = json.loads(raw_json or "{}")
        except json.JSONDecodeError:
            continue
        for qid in value.get("wikidata_qids", []):
            if isinstance(qid, str) and qid.startswith("Q"):
                index[qid].append(birth_fact_id)
    return index


def coordinate(entity: dict[str, Any]) -> tuple[float, float] | None:
    for value in claim_values(entity, CLAIM_COORDINATE):
        if isinstance(value, dict) and value.get("longitude") is not None and value.get("latitude") is not None:
            return float(value["longitude"]), float(value["latitude"])
    return None


def run(db_path: Path, batch_size: int, resume: bool, limit: int | None) -> dict[str, Any]:
    conn = sqlite3.connect(db_path)
    try:
        place_index = load_place_index(conn)
        cursor = ""
        if resume:
            row = conn.execute("SELECT value FROM metadata WHERE key = ?", (CURSOR_KEY,)).fetchone()
            cursor = row[0] if row else ""
        qids = [qid for qid in sorted(place_index) if qid > cursor]
        if limit is not None:
            qids = qids[:limit]
    finally:
        conn.close()

    updated_facts = 0
    places_with_coordinates = 0
    for batch_number, batch in enumerate(chunks(qids, batch_size), start=1):
        entities = fetch_entities(batch, props="claims").get("entities", {})
        conn = sqlite3.connect(db_path)
        try:
            for qid in batch:
                entity = entities.get(qid, {})
                point = coordinate(entity)
                timezone_qids = claim_item_ids(entity, CLAIM_TIMEZONE)
                if point is None:
                    continue
                longitude, latitude = point
                places_with_coordinates += 1
                for birth_fact_id in place_index[qid]:
                    row = conn.execute(
                        "SELECT place_standard_json FROM birth_facts WHERE birth_fact_id = ?",
                        (birth_fact_id,),
                    ).fetchone()
                    place_data = json.loads(row[0] or "{}") if row else {}
                    place_data["coordinate_source"] = f"https://www.wikidata.org/wiki/{qid}"
                    place_data["timezone_qids"] = timezone_qids
                    conn.execute(
                        """
                        UPDATE birth_facts
                        SET longitude = ?, latitude = ?, place_standard_json = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE birth_fact_id = ?
                        """,
                        (longitude, latitude, json.dumps(place_data, ensure_ascii=False), birth_fact_id),
                    )
                    updated_facts += 1
            conn.execute(
                "INSERT OR REPLACE INTO metadata(key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                (CURSOR_KEY, batch[-1]),
            )
            conn.commit()
        finally:
            conn.close()
        print(
            json.dumps(
                {
                    "status": "geocoded_batch",
                    "batch": batch_number,
                    "requested_places": len(batch),
                    "last_qid": batch[-1],
                    "updated_facts_total": updated_facts,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    conn = sqlite3.connect(db_path)
    try:
        batch_id = f"ENRICH_WIKIDATA_BIRTHPLACES_{int(time.time())}"
        conn.execute(
            """
            INSERT OR REPLACE INTO import_batches (
              batch_id, source_id, batch_type, status, record_count, finished_at, notes
            ) VALUES (?, 'OPEN_WIKIDATA_CC0', 'wikidata_birthplace_geo', 'finished', ?, CURRENT_TIMESTAMP, ?)
            """,
            (batch_id, updated_facts, f"Places with coordinates: {places_with_coordinates}."),
        )
        if limit is None:
            conn.execute(
                "INSERT OR REPLACE INTO metadata(key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                ("wikidata_birthplace_enrichment_version", ENRICHMENT_VERSION),
            )
        conn.commit()
    finally:
        conn.close()
    return {
        "database": str(db_path),
        "candidate_places": len(qids),
        "places_with_coordinates": places_with_coordinates,
        "updated_birth_facts": updated_facts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill public birthplace coordinates from Wikidata place entities.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    print(json.dumps(run(args.db, args.batch_size, args.resume, args.limit), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
