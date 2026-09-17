from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "mingli_validation.db"
SCHEMA = ROOT / "database" / "schema.sql"
VIEWS = ROOT / "database" / "views.sql"


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def dump(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


def execute_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    conn.executescript(VIEWS.read_text(encoding="utf-8"))
    conn.execute(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
        ("database_version", "2.0.0"),
    )
    conn.execute(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
        ("scale_target", "10000000"),
    )


def seed_sources(conn: sqlite3.Connection) -> int:
    data = read_json(ROOT / "source_registry.json")
    count = 0
    for item in data.get("registered_sources", []):
        source_id = item["source_id"]
        conn.execute(
            """
            INSERT OR REPLACE INTO source_registry (
              source_id, name, title, url, license, source_type,
              allowed_fields_json, forbidden_fields_json, trust_level,
              refresh_cycle, use_note, status, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_id,
                item.get("title") or source_id,
                item.get("title"),
                item.get("url"),
                infer_license(source_id, item),
                item.get("source_type", "other"),
                dump(item.get("allowed_fields", [])),
                dump(item.get("forbidden_fields", [])),
                item.get("trust_level", "B" if "WIKIDATA" in source_id else "C"),
                item.get("refresh_cycle", "manual"),
                item.get("use"),
                item.get("status"),
                item.get("notes"),
            ),
        )
        count += 1
    return count


def infer_license(source_id: str, item: dict[str, Any]) -> str:
    if "WIKIDATA" in source_id:
        return "CC0"
    if item.get("source_type") == "private_case_database":
        return "restricted"
    return item.get("license", "unknown")


def seed_knowledge(conn: sqlite3.Connection) -> tuple[int, int]:
    data = read_json(ROOT / "knowledge_base.json")
    source_count = 0
    rule_count = 0
    for item in data.get("theory_sources", []):
        conn.execute(
            """
            INSERT OR REPLACE INTO theory_sources (
              source_id, tradition, source_type, topic, summary,
              applicable_modules_json, limitations, confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["source_id"],
                item["tradition"],
                item["source_type"],
                item["topic"],
                item["summary"],
                dump(item.get("applicable_modules", [])),
                item.get("limitations"),
                item.get("confidence", "medium"),
            ),
        )
        source_count += 1

    for item in data.get("knowledge_rules", []):
        conn.execute(
            """
            INSERT OR REPLACE INTO knowledge_rules (
              rule_id, system, topic, rule_summary, usage_scope, priority,
              conflict_policy, source_ids_json, applicable_conditions_json,
              forbidden_conditions_json, validation_status, confidence_score
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["rule_id"],
                item["system"],
                item["topic"],
                item["rule_summary"],
                item["usage_scope"],
                item["priority"],
                item["conflict_policy"],
                dump(item.get("source_ids", [])),
                dump(item.get("applicable_conditions", [])),
                dump(item.get("forbidden_conditions", [])),
                item.get("validation_status", "unverified"),
                float(item.get("confidence_score", 0.5)),
            ),
        )
        rule_count += 1
    return source_count, rule_count


def seed_local_persons(conn: sqlite3.Connection) -> int:
    data = read_json(ROOT / "seed_records.json")
    count = 0
    for person in data.get("persons", []):
        birth = person.get("birth", {})
        conn.execute(
            """
            INSERT OR REPLACE INTO local_persons (
              person_id, name, gender, calendar_type, birth_year, birth_month,
              birth_day, is_leap_lunar_month, time_text, hour_branch,
              time_accuracy, timezone, birthplace_json, known_chart_json,
              privacy_level, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                person["person_id"],
                person["name"],
                person.get("gender", "unknown"),
                birth.get("calendar_type", "unknown"),
                birth.get("year"),
                birth.get("month"),
                birth.get("day"),
                bool_to_int(birth.get("is_leap_lunar_month")),
                birth.get("time_text"),
                birth.get("hour_branch"),
                birth.get("time_accuracy", "unknown"),
                birth.get("timezone"),
                dump(person.get("birthplace", {})),
                dump(person.get("known_chart", {})),
                person.get("privacy_level", "local_private"),
                person.get("notes"),
            ),
        )
        birth_fact_id = f"BF_{person['person_id']}"
        conn.execute(
            """
            INSERT OR REPLACE INTO birth_facts (
              birth_fact_id, subject_type, subject_id, raw_birth_text,
              date_standard, date_precision, calendar_type, time_text,
              time_precision, place_raw, place_standard_json, timezone,
              source_id, confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                birth_fact_id,
                "local_person",
                person["person_id"],
                build_birth_text(person),
                person.get("known_chart", {}).get("solar_date"),
                "day" if person.get("known_chart", {}).get("solar_date") else "unknown",
                birth.get("calendar_type", "unknown"),
                birth.get("time_text"),
                birth.get("time_accuracy", "unknown"),
                person.get("birthplace", {}).get("raw"),
                dump(person.get("birthplace", {})),
                birth.get("timezone"),
                "PRACTICE_USER_CASES_LOCAL",
                "medium",
            ),
        )
        count += 1
    return count


def bool_to_int(value: Any) -> int | None:
    if value is None:
        return None
    return 1 if bool(value) else 0


def build_birth_text(person: dict[str, Any]) -> str:
    birth = person.get("birth", {})
    date = f"{birth.get('calendar_type', 'unknown')} {birth.get('year')}-{birth.get('month')}-{birth.get('day')}"
    time = birth.get("time_text") or "时辰不详"
    return f"{date} {time}"


def seed_cases(conn: sqlite3.Connection) -> tuple[int, int, int]:
    data = read_json(ROOT / "case_practice_records.json")
    case_count = 0
    correction_count = 0
    qc_count = 0
    for item in data.get("case_studies", []):
        conn.execute(
            """
            INSERT OR REPLACE INTO case_studies (
              case_id, subject_type, subject_id, name, chart_snapshot_json,
              model_tags_json, report_ids_json, known_life_events_json,
              validation_status, lessons_json, similarity_keys_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["case_id"],
                "local_person",
                item["person_id"],
                item["name"],
                dump(item.get("chart_snapshot", {})),
                dump(item.get("model_tags", [])),
                dump(item.get("report_ids", [])),
                dump(item.get("known_life_events", [])),
                item.get("validation_status", "unverified"),
                dump(item.get("lessons", [])),
                dump(item.get("similarity_keys", [])),
            ),
        )
        case_count += 1

    for item in data.get("correction_records", []):
        conn.execute(
            """
            INSERT OR REPLACE INTO correction_records (
              correction_id, subject_type, subject_id, case_id, correction_type,
              before_json, after_json, reason, impact, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["correction_id"],
                "local_person",
                item.get("person_id"),
                item.get("case_id"),
                item["correction_type"],
                dump(item.get("before", {})),
                dump(item.get("after", {})),
                item["reason"],
                item["impact"],
                item.get("created_at"),
            ),
        )
        correction_count += 1

    for item in data.get("report_quality_checks", []):
        conn.execute(
            """
            INSERT OR REPLACE INTO report_quality_checks (
              check_id, report_id, subject_type, subject_id, items_json,
              quality_grade, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["check_id"],
                item.get("report_id"),
                "local_person",
                item.get("person_id", "template"),
                dump(item.get("items", {})),
                item.get("quality_grade", "C"),
                item.get("notes"),
            ),
        )
        qc_count += 1
    return case_count, correction_count, qc_count


def create_database(db_path: Path, reset: bool) -> dict[str, int]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if reset and db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        execute_schema(conn)
        source_count = seed_sources(conn)
        theory_count, rule_count = seed_knowledge(conn)
        person_count = seed_local_persons(conn)
        case_count, correction_count, qc_count = seed_cases(conn)
        conn.commit()
    finally:
        conn.close()

    return {
        "sources": source_count,
        "theory_sources": theory_count,
        "knowledge_rules": rule_count,
        "local_persons": person_count,
        "case_studies": case_count,
        "correction_records": correction_count,
        "quality_checks": qc_count,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize Mingli validation database.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    counts = create_database(args.db, args.reset)
    print(json.dumps({"db": str(args.db), "counts": counts}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
