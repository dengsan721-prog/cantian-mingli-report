from __future__ import annotations

import argparse
import json
import sqlite3
import time
import urllib.parse
import urllib.request
from urllib.error import HTTPError
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "mingli_validation.db"
DEFAULT_QIDS = ROOT / "pipeline" / "wikidata_seed_qids.txt"
API = "https://www.wikidata.org/w/api.php"
SOURCE_ID = "OPEN_WIKIDATA_CC0"

CLAIM_BIRTH = "P569"
CLAIM_DEATH = "P570"
CLAIM_BIRTH_PLACE = "P19"
CLAIM_OCCUPATION = "P106"
CLAIM_COUNTRY = "P27"


def dump(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


def read_qids(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index:index + size] for index in range(0, len(values), size)]


def api_get(params: dict[str, str], retries: int = 6, pause: float = 0.5) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f"{API}?{query}",
        headers={"User-Agent": "MingliValidationEntities/0.1 (local research; contact: local)"},
    )
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                if pause:
                    time.sleep(pause)
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            last_error = exc
            if exc.code == 429 and attempt < retries:
                retry_after = exc.headers.get("Retry-After")
                wait = int(retry_after) if retry_after and retry_after.isdigit() else min(90, 10 * attempt)
                time.sleep(wait)
                continue
            if attempt < retries:
                time.sleep(attempt * 3)
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(attempt * 3)
    raise RuntimeError("Wikidata API request failed") from last_error


def fetch_entities(qids: list[str], props: str = "labels|claims") -> dict[str, Any]:
    payload: dict[str, Any] = {"entities": {}}
    for batch in chunks(qids, 50):
        data = api_get(
            {
                "action": "wbgetentities",
                "ids": "|".join(batch),
                "props": props,
                "languages": "zh|en",
                "languagefallback": "1",
                "format": "json",
            }
        )
        payload["entities"].update(data.get("entities", {}))
    return payload


def label(entity: dict[str, Any]) -> str | None:
    labels = entity.get("labels", {})
    if "zh" in labels:
        return labels["zh"].get("value")
    if "en" in labels:
        return labels["en"].get("value")
    return None


def claim_values(entity: dict[str, Any], prop: str) -> list[Any]:
    claims = entity.get("claims", {}).get(prop, [])
    values = []
    for claim in claims:
        mainsnak = claim.get("mainsnak", {})
        datavalue = mainsnak.get("datavalue")
        if datavalue is not None:
            values.append(datavalue.get("value"))
    return values


def claim_time(entity: dict[str, Any], prop: str) -> str | None:
    values = claim_values(entity, prop)
    if not values:
        return None
    value = values[0]
    if isinstance(value, dict):
        return normalize_wikidata_time(value.get("time"))
    return None


def normalize_wikidata_time(value: str | None) -> str | None:
    if not value:
        return None
    clean = value.lstrip("+")
    return clean.replace("T00:00:00Z", "")


def claim_item_ids(entity: dict[str, Any], prop: str) -> list[str]:
    ids: list[str] = []
    for value in claim_values(entity, prop):
        if isinstance(value, dict) and value.get("entity-type") == "item":
            ids.append(f"Q{value.get('numeric-id')}")
    return ids


def date_precision(value: str | None) -> str:
    if not value:
        return "unknown"
    if len(value) >= 10 and value[4] == "-" and value[7] == "-" and value[5:7] != "00" and value[8:10] != "00":
        return "day"
    if len(value) >= 7 and value[4] == "-" and value[5:7] != "00":
        return "month"
    if len(value) >= 4:
        return "year"
    return "unknown"


def quality_level(dob: str | None, birth_place: str | None) -> str:
    if dob and birth_place:
        return "L2"
    if dob:
        return "L1"
    return "L0"


def collect_linked_labels(entities: dict[str, Any]) -> dict[str, str]:
    linked: set[str] = set()
    for entity in entities.values():
        if "missing" in entity:
            continue
        linked.update(claim_item_ids(entity, CLAIM_BIRTH_PLACE))
        linked.update(claim_item_ids(entity, CLAIM_OCCUPATION))
        linked.update(claim_item_ids(entity, CLAIM_COUNTRY))
    if not linked:
        return {}
    linked_entities = fetch_entities(sorted(linked), props="labels").get("entities", {})
    return {qid: label(entity) or qid for qid, entity in linked_entities.items() if "missing" not in entity}


def upsert_entities(conn: sqlite3.Connection, entities: dict[str, Any], batch_id: str) -> int:
    labels = collect_linked_labels(entities)
    count = 0
    death_events = 0
    for qid, entity in entities.items():
        if "missing" in entity:
            continue
        public_person_id = f"WD_{qid}"
        name = label(entity) or qid
        dob = claim_time(entity, CLAIM_BIRTH)
        dod = claim_time(entity, CLAIM_DEATH)
        birth_place_ids = claim_item_ids(entity, CLAIM_BIRTH_PLACE)
        occupation_ids = claim_item_ids(entity, CLAIM_OCCUPATION)
        country_ids = claim_item_ids(entity, CLAIM_COUNTRY)
        birth_place = labels.get(birth_place_ids[0]) if birth_place_ids else None
        occupations = [labels.get(item, item) for item in occupation_ids]
        countries = [labels.get(item, item) for item in country_ids]

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
                dump({"wikidata_uri": f"http://www.wikidata.org/entity/{qid}"}),
                name,
                dump([]),
                dump({"preferred": name}),
                0 if dod else None,
                dump(occupations),
                dump([]),
                dump(countries),
                "public_figure",
                dump([SOURCE_ID]),
                quality_level(dob, birth_place),
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
                dob,
                dob,
                date_precision(dob),
                "solar",
                None,
                "unknown",
                birth_place,
                dump({"raw": birth_place, "wikidata_qids": birth_place_ids}),
                f"https://www.wikidata.org/wiki/{qid}",
                SOURCE_ID,
                "medium" if dob else "low",
            ),
        )
        if dod:
            conn.execute(
                """
                INSERT OR REPLACE INTO life_events_public (
                  event_id, public_person_id, event_type, event_date,
                  event_precision, event_summary, source_url, source_id,
                  confidence, sensitivity, allowed_for_modeling
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"EVT_WD_{qid}_DEATH",
                    public_person_id,
                    "death",
                    dod,
                    date_precision(dod),
                    f"{name} death date recorded in Wikidata.",
                    f"https://www.wikidata.org/wiki/{qid}",
                    SOURCE_ID,
                    "medium",
                    "low",
                    1,
                ),
            )
            death_events += 1
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
            "wikidata_entities",
            "finished",
            count,
            f"Imported entities via Wikidata API. Death events: {death_events}.",
        ),
    )
    return count


def run(db_path: Path, qids_path: Path) -> dict[str, Any]:
    qids = read_qids(qids_path)
    batch_id = f"IMPORT_WIKIDATA_ENTITIES_{int(time.time())}"
    entities = fetch_entities(qids).get("entities", {})
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        count = upsert_entities(conn, entities, batch_id)
        conn.commit()
    finally:
        conn.close()
    return {"batch_id": batch_id, "requested_qids": len(qids), "imported_people": count, "db": str(db_path)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Import public person entities from Wikidata API by QID list.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--qids", type=Path, default=DEFAULT_QIDS)
    args = parser.parse_args()
    print(json.dumps(run(args.db, args.qids), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
