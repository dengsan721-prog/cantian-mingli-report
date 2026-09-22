from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
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
CLAIM_GENDER = "P21"
CLAIM_POSITION = "P39"
CLAIM_AWARD = "P166"
CLAIM_SPOUSE = "P26"
CLAIM_EDUCATION = "P69"
QUALIFIER_START = "P580"
QUALIFIER_POINT_IN_TIME = "P585"

GENDER_MAP = {
    "Q6581097": "male",
    "Q6581072": "female",
}


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
    batches = chunks(qids, 50)
    if not batches:
        return payload

    def fetch_batch(batch: list[str]) -> dict[str, Any]:
        return api_get(
            {
                "action": "wbgetentities",
                "ids": "|".join(batch),
                "props": props,
                "languages": "zh|en",
                "languagefallback": "1",
                "format": "json",
            }
        )

    with ThreadPoolExecutor(max_workers=min(8, len(batches))) as executor:
        for data in executor.map(fetch_batch, batches):
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
        return normalize_wikidata_time(value.get("time"), value.get("precision"))
    return None


def normalize_wikidata_time(value: str | None, precision: int | None = None) -> str | None:
    if not value or precision is None or precision < 9:
        return None
    clean = value.lstrip("+")
    calendar_date = clean.split("T", 1)[0]
    year, month, day = calendar_date.rsplit("-", 2)
    # Wikidata may encode a year-only value with January 1 as its placeholder.
    if precision == 9:
        return f"{year}-00-00"
    if precision == 10:
        return f"{year}-{month}-00"
    return calendar_date


def claim_item_ids(entity: dict[str, Any], prop: str) -> list[str]:
    ids: list[str] = []
    for value in claim_values(entity, prop):
        if isinstance(value, dict) and value.get("entity-type") == "item":
            ids.append(f"Q{value.get('numeric-id')}")
    return ids


def qualifier_time(statement: dict[str, Any], *properties: str) -> str | None:
    qualifiers = statement.get("qualifiers", {})
    for prop in properties:
        for qualifier in qualifiers.get(prop, []):
            value = qualifier.get("datavalue", {}).get("value")
            if isinstance(value, dict):
                normalized = normalize_wikidata_time(value.get("time"), value.get("precision"))
                if normalized:
                    return normalized
    return None


def item_statements(entity: dict[str, Any], prop: str) -> list[tuple[str, dict[str, Any]]]:
    statements: list[tuple[str, dict[str, Any]]] = []
    for statement in entity.get("claims", {}).get(prop, []):
        value = statement.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, dict) and value.get("entity-type") == "item":
            statements.append((f"Q{value.get('numeric-id')}", statement))
    return statements


def structured_event_id(
    qid: str,
    event_type: str,
    target_qid: str,
    statement: dict[str, Any],
    event_date: str,
    index: int,
) -> str:
    statement_key = statement.get("id") or f"{target_qid}|{event_date}|{index}"
    digest = hashlib.sha1(str(statement_key).encode("utf-8")).hexdigest()[:16]
    return f"EVT_WD_{qid}_{event_type.upper()}_{digest}"


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
        linked.update(claim_item_ids(entity, CLAIM_POSITION))
        linked.update(claim_item_ids(entity, CLAIM_AWARD))
        linked.update(claim_item_ids(entity, CLAIM_SPOUSE))
        linked.update(claim_item_ids(entity, CLAIM_EDUCATION))
    if not linked:
        return {}
    linked_entities = fetch_entities(sorted(linked), props="labels").get("entities", {})
    return {qid: label(entity) or qid for qid, entity in linked_entities.items() if "missing" not in entity}


def upsert_dated_events(conn: sqlite3.Connection, entities: dict[str, Any], batch_id: str) -> tuple[int, int]:
    """Fast backfill path that avoids downloading labels for every linked item."""
    processed = 0
    structured_events = 0
    event_specs = (
        (CLAIM_POSITION, "office", "held position", "low"),
        (CLAIM_AWARD, "award", "received award", "low"),
        (CLAIM_SPOUSE, "marriage", "marriage recorded with", "medium"),
        (CLAIM_EDUCATION, "education", "education recorded at", "low"),
    )
    for qid, entity in entities.items():
        if "missing" in entity:
            continue
        public_person_id = f"WD_{qid}"
        if conn.execute("SELECT 1 FROM public_persons WHERE public_person_id = ?", (public_person_id,)).fetchone() is None:
            continue
        name_row = conn.execute(
            "SELECT primary_name FROM public_persons WHERE public_person_id = ?",
            (public_person_id,),
        ).fetchone()
        name = name_row[0] if name_row else qid
        gender_ids = claim_item_ids(entity, CLAIM_GENDER)
        gender = GENDER_MAP.get(gender_ids[0], "unknown") if gender_ids else "unknown"
        conn.execute(
            "UPDATE public_persons SET gender = ?, updated_at = CURRENT_TIMESTAMP WHERE public_person_id = ?",
            (gender, public_person_id),
        )
        conn.execute(
            """
            DELETE FROM life_events_public
            WHERE public_person_id = ?
              AND source_id = ?
              AND event_type IN ('office', 'award', 'marriage', 'education')
            """,
            (public_person_id, SOURCE_ID),
        )
        for prop, event_type, action, sensitivity in event_specs:
            for index, (target_qid, statement) in enumerate(item_statements(entity, prop)):
                event_date = qualifier_time(statement, QUALIFIER_START, QUALIFIER_POINT_IN_TIME)
                if not event_date:
                    continue
                conn.execute(
                    """
                    INSERT OR REPLACE INTO life_events_public (
                      event_id, public_person_id, event_type, event_date,
                      event_precision, event_summary, source_url, source_id,
                      confidence, sensitivity, allowed_for_modeling
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        structured_event_id(qid, event_type, target_qid, statement, event_date, index),
                        public_person_id,
                        event_type,
                        event_date,
                        date_precision(event_date),
                        f"{name} {action} Wikidata item {target_qid}.",
                        f"https://www.wikidata.org/wiki/{qid}",
                        SOURCE_ID,
                        "medium",
                        sensitivity,
                        1,
                    ),
                )
                structured_events += 1
        processed += 1

    conn.execute(
        """
        INSERT OR REPLACE INTO import_batches (
          batch_id, source_id, batch_type, status, record_count, finished_at, notes
        ) VALUES (?, ?, 'wikidata_dated_events', 'finished', ?, CURRENT_TIMESTAMP, ?)
        """,
        (batch_id, SOURCE_ID, processed, f"Fast event backfill. Structured dated events upserted: {structured_events}."),
    )
    return processed, structured_events


def upsert_entities(conn: sqlite3.Connection, entities: dict[str, Any], batch_id: str) -> int:
    labels = collect_linked_labels(entities)
    count = 0
    death_events = 0
    structured_events = 0
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
        gender_ids = claim_item_ids(entity, CLAIM_GENDER)
        gender = GENDER_MAP.get(gender_ids[0], "unknown") if gender_ids else "unknown"

        conn.execute(
            """
            INSERT OR REPLACE INTO public_persons (
              public_person_id, wikidata_qid, external_ids_json, primary_name,
              aliases_json, language_labels_json, is_living, occupations_json,
              fields_json, countries_json, gender, privacy_class, source_ids_json,
              quality_level, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
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
                gender,
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

        conn.execute(
            """
            DELETE FROM life_events_public
            WHERE public_person_id = ?
              AND source_id = ?
              AND event_type IN ('office', 'award', 'marriage', 'education')
            """,
            (public_person_id, SOURCE_ID),
        )

        event_specs = (
            (CLAIM_POSITION, "office", "held position", "low"),
            (CLAIM_AWARD, "award", "received award", "low"),
            (CLAIM_SPOUSE, "marriage", "marriage recorded with", "medium"),
            (CLAIM_EDUCATION, "education", "education recorded at", "low"),
        )
        for prop, event_type, action, sensitivity in event_specs:
            for index, (target_qid, statement) in enumerate(item_statements(entity, prop)):
                event_date = qualifier_time(statement, QUALIFIER_START, QUALIFIER_POINT_IN_TIME)
                if not event_date:
                    continue
                target_label = labels.get(target_qid, target_qid)
                conn.execute(
                    """
                    INSERT OR REPLACE INTO life_events_public (
                      event_id, public_person_id, event_type, event_date,
                      event_precision, event_summary, source_url, source_id,
                      confidence, sensitivity, allowed_for_modeling
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        structured_event_id(qid, event_type, target_qid, statement, event_date, index),
                        public_person_id,
                        event_type,
                        event_date,
                        date_precision(event_date),
                        f"{name} {action} {target_label}.",
                        f"https://www.wikidata.org/wiki/{qid}",
                        SOURCE_ID,
                        "medium",
                        sensitivity,
                        1,
                    ),
                )
                structured_events += 1
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
            f"Imported entities via Wikidata API. Death events: {death_events}. Structured dated events: {structured_events}.",
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
        columns = {row[1] for row in conn.execute("PRAGMA table_info(public_persons)")}
        if "gender" not in columns:
            conn.execute("ALTER TABLE public_persons ADD COLUMN gender TEXT NOT NULL DEFAULT 'unknown'")
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
