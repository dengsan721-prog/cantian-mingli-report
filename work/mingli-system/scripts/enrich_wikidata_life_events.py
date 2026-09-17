from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from import_wikidata_entities import fetch_entities, upsert_dated_events
from init_database import DEFAULT_DB


ENRICHMENT_VERSION = "wikidata-dated-events-v1"
CURSOR_KEY = f"{ENRICHMENT_VERSION}_cursor"


def chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index:index + size] for index in range(0, len(values), size)]


def ensure_schema(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(public_persons)")}
    if "gender" not in columns:
        conn.execute("ALTER TABLE public_persons ADD COLUMN gender TEXT NOT NULL DEFAULT 'unknown'")


def run(db_path: Path, batch_size: int, resume: bool, limit: int | None) -> dict[str, Any]:
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        ensure_schema(conn)
        cursor = ""
        if resume:
            row = conn.execute("SELECT value FROM metadata WHERE key = ?", (CURSOR_KEY,)).fetchone()
            cursor = row[0] if row else ""
        query = "SELECT wikidata_qid FROM public_persons WHERE wikidata_qid IS NOT NULL AND wikidata_qid > ? ORDER BY wikidata_qid"
        params: list[Any] = [cursor]
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        qids = [row[0] for row in conn.execute(query, params).fetchall()]
        conn.commit()
    finally:
        conn.close()

    processed = 0
    completed_batches = 0
    for batch_index, batch in enumerate(chunks(qids, batch_size), start=1):
        entities = fetch_entities(batch, props="claims").get("entities", {})
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            ensure_schema(conn)
            batch_id = f"ENRICH_WIKIDATA_EVENTS_{int(time.time())}_{batch_index}"
            imported, event_count = upsert_dated_events(conn, entities, batch_id)
            conn.execute("INSERT OR REPLACE INTO metadata(key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)", (CURSOR_KEY, batch[-1]))
            conn.commit()
        finally:
            conn.close()
        processed += imported
        completed_batches += 1
        print(
            json.dumps(
                {
                    "status": "enriched_batch",
                    "batch": batch_index,
                    "requested_qids": len(batch),
                    "processed_people": imported,
                    "dated_events_upserted": event_count,
                    "last_qid": batch[-1],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    conn = sqlite3.connect(db_path)
    try:
        if not limit and processed == len(qids):
            conn.execute("INSERT OR REPLACE INTO metadata(key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)", ("wikidata_event_enrichment_version", ENRICHMENT_VERSION))
        event_counts = dict(conn.execute("SELECT event_type, COUNT(*) FROM life_events_public GROUP BY event_type").fetchall())
        conn.commit()
    finally:
        conn.close()
    return {
        "database": str(db_path),
        "enrichment_version": ENRICHMENT_VERSION,
        "candidate_people": len(qids),
        "processed_people": processed,
        "completed_batches": completed_batches,
        "event_counts": event_counts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill dated public life events from Wikidata claim qualifiers.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    print(json.dumps(run(args.db, args.batch_size, args.resume, args.limit), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
