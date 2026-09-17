from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

from init_database import DEFAULT_DB


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "database" / "schema.sql"
VIEWS = ROOT / "database" / "views.sql"
SPLIT_VERSION = "birth-fact-hash-v1"
QUALITY_VERSION = "precision-foundation-v1"

ALL_MODULES = {
    "basic_profile",
    "source_audit",
    "three_pillars",
    "day_master",
    "seasonal_climate",
    "broad_tendencies",
    "birthplace_context",
    "hour_pillar",
    "complete_ten_gods",
    "relationships_children_late_life",
    "luck_cycles",
    "precise_timing",
    "outcome_rule_calibration",
}


def dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def year_from_date(value: str | None) -> int | None:
    if not value or len(value) < 4:
        return None
    try:
        return int(value[:4])
    except ValueError:
        return None


def source_score(trust_level: str | None, confidence: str | None) -> int:
    trust_scores = {"A": 90, "B": 75, "C": 60, "D": 40}
    confidence_adjustment = {"high": 5, "medium": 0, "low": -15}
    return max(0, min(100, trust_scores.get(trust_level or "C", 60) + confidence_adjustment.get(confidence or "medium", 0)))


def birth_score(fact: sqlite3.Row) -> tuple[int, list[str]]:
    date_scores = {"unknown": 0, "year": 20, "month": 35, "day": 55, "hour": 60}
    time_scores = {"unknown": 0, "boundary": 10, "approximate": 20, "exact": 25}
    reasons: list[str] = []
    score = date_scores.get(fact["date_precision"], 0)
    score += time_scores.get(fact["time_precision"], 0)
    if fact["place_raw"]:
        score += 10
    else:
        reasons.append("PLACE_MISSING")
    if fact["longitude"] is not None and fact["latitude"] is not None:
        score += 5
    else:
        reasons.append("COORDINATES_MISSING")
    if fact["timezone"]:
        score += 5
    else:
        reasons.append("TIMEZONE_MISSING")
    if fact["date_precision"] != "day":
        reasons.append("DATE_NOT_DAY_PRECISION")
    if fact["time_precision"] not in {"exact", "approximate"}:
        reasons.append("TIME_UNKNOWN_OR_UNRELIABLE")
    if fact["time_precision"] == "approximate":
        reasons.append("TIME_APPROXIMATE")
    if fact["calendar_verification_status"] != "verified":
        score -= 5
        reasons.append("CALENDAR_NOT_VERIFIED")
    if fact["time_precision"] in {"exact", "approximate"} and fact["time_standard_status"] != "verified":
        score -= 5
        reasons.append("HISTORICAL_TIME_STANDARD_NOT_VERIFIED")
    if fact["conflict_group_id"]:
        score -= 15
        reasons.append("CONFLICTING_BIRTH_FACTS")
    year = year_from_date(fact["date_standard"])
    if year is not None and year < 1582:
        score -= 15
        reasons.append("HISTORICAL_CALENDAR_CONVERSION_REQUIRED")
    return max(0, min(100, score)), reasons


def event_score(event_count: int, event_types: int, dated_events: int) -> tuple[int, list[str]]:
    score = min(40, event_count * 8) + min(30, event_types * 10) + min(30, dated_events * 5)
    reasons: list[str] = []
    if event_count < 5:
        reasons.append("FEWER_THAN_FIVE_EVENTS")
    if event_types < 3:
        reasons.append("FEWER_THAN_THREE_EVENT_TYPES")
    if dated_events < 3:
        reasons.append("INSUFFICIENT_DATED_EVENTS")
    return min(100, score), reasons


def quality_level(fact: sqlite3.Row, event_count: int, event_types: int) -> str:
    has_day = fact["date_precision"] == "day"
    has_time = fact["time_precision"] in {"exact", "approximate"}
    has_exact_time = fact["time_precision"] == "exact"
    has_place = bool(fact["place_raw"])
    has_geo = fact["longitude"] is not None and fact["latitude"] is not None and bool(fact["timezone"])
    standards_verified = (
        fact["calendar_verification_status"] == "verified"
        and fact["time_standard_status"] == "verified"
    )
    if has_day and has_exact_time and has_place and has_geo and standards_verified and event_count >= 5 and event_types >= 3:
        return "L4"
    if has_day and has_time and has_place:
        return "L3"
    if has_day and has_place:
        return "L2"
    if has_day:
        return "L1"
    return "L0"


def module_policy(level: str, reasons: list[str]) -> tuple[str, list[str], list[str]]:
    allowed = {"basic_profile", "source_audit"}
    max_report_level = "intake_only"
    if level in {"L1", "L2", "L3", "L4"}:
        allowed.update({"three_pillars", "day_master", "seasonal_climate", "broad_tendencies"})
        max_report_level = "three_pillar"
    if level in {"L2", "L3", "L4"}:
        allowed.add("birthplace_context")
        max_report_level = "three_pillar_contextual"
    if level in {"L3", "L4"}:
        allowed.update({"hour_pillar", "complete_ten_gods", "relationships_children_late_life", "luck_cycles"})
        max_report_level = "four_pillar_provisional"
    if level == "L4":
        allowed.update({"precise_timing", "outcome_rule_calibration"})
        max_report_level = "calibrated_four_pillar"
    if "HISTORICAL_CALENDAR_CONVERSION_REQUIRED" in reasons:
        allowed.discard("precise_timing")
        allowed.discard("outcome_rule_calibration")
        if max_report_level == "calibrated_four_pillar":
            max_report_level = "four_pillar_provisional"
    return max_report_level, sorted(allowed), sorted(ALL_MODULES - allowed)


def split_for(public_person_id: str) -> tuple[str, str]:
    digest = hashlib.sha256(f"{SPLIT_VERSION}:{public_person_id}".encode("utf-8")).hexdigest()
    bucket = int(digest[:8], 16) % 100
    if bucket < 70:
        split = "train"
    elif bucket < 85:
        split = "validation"
    else:
        split = "test"
    return split, digest


def era_bucket(date_standard: str | None) -> str:
    year = year_from_date(date_standard)
    if year is None:
        return "unknown"
    if year < 1582:
        return "pre_1582"
    if year < 1850:
        return "1582_1849"
    if year < 1950:
        return "1850_1949"
    return "1950_plus"


def migrate(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    birth_columns = {row[1] for row in conn.execute("PRAGMA table_info(birth_facts)")}
    for name, definition in (
        ("calendar_model", "TEXT"),
        ("calendar_verification_status", "TEXT NOT NULL DEFAULT 'unverified'"),
        ("time_standard_status", "TEXT NOT NULL DEFAULT 'unverified'"),
    ):
        if name not in birth_columns:
            conn.execute(f"ALTER TABLE birth_facts ADD COLUMN {name} {definition}")
    assignment_columns = {row[1] for row in conn.execute("PRAGMA table_info(validation_assignments)")}
    if "era_bucket" not in assignment_columns:
        conn.execute("ALTER TABLE validation_assignments ADD COLUMN era_bucket TEXT NOT NULL DEFAULT 'unknown'")
    conn.executescript(VIEWS.read_text(encoding="utf-8"))
    conn.execute("INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)", ("quality_model_version", QUALITY_VERSION))
    conn.execute("INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)", ("validation_split_version", SPLIT_VERSION))
    conn.execute(
        """
        INSERT OR REPLACE INTO validation_protocols (
          protocol_id, rule_id, protocol_type, hypothesis,
          cohort_definition_json, target_event_types_json,
          forecast_window_json, baseline_spec_json, primary_metric,
          minimum_sample_size, split_version, frozen_rule_version,
          multiple_testing_family, status, preregistered_at
        ) VALUES (?, ?, 'safety', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', CURRENT_TIMESTAMP)
        """,
        (
            "PROTO_NO_HOUR_DOWNGRADE_V1",
            "KR_002_NO_HOUR_NO_FULL_DETAIL",
            "Records without reliable birth time are never admitted to hour-dependent report modules.",
            dump({"time_precision": ["unknown", "boundary"]}),
            dump([]),
            dump({}),
            dump({"type": "mandatory_policy", "expected_rate": 1.0}),
            "policy_compliance_rate",
            500,
            SPLIT_VERSION,
            QUALITY_VERSION,
            "safety_controls",
        ),
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO validation_protocols (
          protocol_id, rule_id, protocol_type, hypothesis,
          cohort_definition_json, target_event_types_json,
          forecast_window_json, baseline_spec_json, primary_metric,
          minimum_sample_size, split_version, frozen_rule_version,
          multiple_testing_family, status
        ) VALUES (?, NULL, 'outcome', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'data_collection')
        """,
        (
            "PROTO_OUTCOME_TEMPLATE_V1",
            "A frozen traditional rule must outperform a matched non-astrological baseline on unseen people.",
            dump({"quality_level": "L4", "minimum_events": 5, "minimum_event_types": 3}),
            dump(["office", "award", "marriage", "education", "death"]),
            dump({"must_be_defined_per_rule": True}),
            dump({"required": True, "examples": ["age_rate", "occupation", "country", "era"]}),
            "predeclared_per_rule",
            500,
            SPLIT_VERSION,
            "unfrozen",
            "outcome_rules",
        ),
    )


def assess_public_people(conn: sqlite3.Connection) -> tuple[int, Counter[str], Counter[str]]:
    rows = conn.execute(
        """
        SELECT
          pp.public_person_id AS subject_id,
          bf.date_standard,
          bf.date_precision,
          bf.calendar_verification_status,
          bf.time_precision,
          bf.time_standard_status,
          bf.place_raw,
          bf.longitude,
          bf.latitude,
          bf.timezone,
          bf.conflict_group_id,
          bf.confidence,
          sr.trust_level,
          COUNT(DISTINCT CASE WHEN le.allowed_for_modeling = 1 THEN le.event_id END) AS event_count,
          COUNT(DISTINCT CASE WHEN le.allowed_for_modeling = 1 THEN le.event_type END) AS event_types,
          COUNT(DISTINCT CASE WHEN le.allowed_for_modeling = 1 AND le.event_precision != 'unknown' THEN le.event_id END) AS dated_events
        FROM public_persons pp
        LEFT JOIN birth_facts bf
          ON bf.subject_type = 'public_person' AND bf.subject_id = pp.public_person_id
        LEFT JOIN source_registry sr ON sr.source_id = bf.source_id
        LEFT JOIN life_events_public le ON le.public_person_id = pp.public_person_id
        GROUP BY pp.public_person_id
        """
    ).fetchall()
    levels: Counter[str] = Counter()
    report_levels: Counter[str] = Counter()
    for fact in rows:
        b_score, birth_reasons = birth_score(fact)
        e_score, event_reasons = event_score(fact["event_count"], fact["event_types"], fact["dated_events"])
        s_score = source_score(fact["trust_level"], fact["confidence"])
        level = quality_level(fact, fact["event_count"], fact["event_types"])
        reasons = sorted(set(birth_reasons + event_reasons))
        max_report_level, allowed, blocked = module_policy(level, reasons)
        overall = round(b_score * 0.6 + e_score * 0.3 + s_score * 0.1)
        subject_id = fact["subject_id"]
        conn.execute(
            """
            INSERT OR REPLACE INTO data_quality_assessments (
              assessment_id, subject_type, subject_id, birth_score, event_score,
              source_score, overall_score, quality_level, max_report_level,
              allowed_modules_json, blocked_modules_json, reason_codes_json,
              assessed_at
            ) VALUES (?, 'public_person', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                f"DQA_PUBLIC_{subject_id}", subject_id, b_score, e_score, s_score,
                overall, level, max_report_level, dump(allowed), dump(blocked), dump(reasons),
            ),
        )
        conn.execute("UPDATE public_persons SET quality_level = ?, updated_at = CURRENT_TIMESTAMP WHERE public_person_id = ?", (level, subject_id))
        split, digest = split_for(subject_id)
        conn.execute(
            """
            INSERT OR REPLACE INTO validation_assignments (
              public_person_id, split_version, dataset_split, era_bucket,
              assignment_hash, assigned_at
            ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (subject_id, SPLIT_VERSION, split, era_bucket(fact["date_standard"]), digest),
        )
        levels[level] += 1
        report_levels[max_report_level] += 1
    return len(rows), levels, report_levels


def assess_local_people(conn: sqlite3.Connection) -> tuple[int, Counter[str]]:
    rows = conn.execute(
        """
        SELECT
          lp.person_id AS subject_id,
          bf.date_standard,
          bf.date_precision,
          bf.calendar_verification_status,
          bf.time_precision,
          bf.time_standard_status,
          bf.place_raw,
          bf.longitude,
          bf.latitude,
          bf.timezone,
          bf.conflict_group_id,
          bf.confidence,
          sr.trust_level,
          0 AS event_count,
          0 AS event_types,
          0 AS dated_events
        FROM local_persons lp
        LEFT JOIN birth_facts bf
          ON bf.subject_type = 'local_person' AND bf.subject_id = lp.person_id
        LEFT JOIN source_registry sr ON sr.source_id = bf.source_id
        """
    ).fetchall()
    levels: Counter[str] = Counter()
    for fact in rows:
        b_score, birth_reasons = birth_score(fact)
        e_score, event_reasons = event_score(0, 0, 0)
        s_score = max(90, source_score(fact["trust_level"], fact["confidence"]))
        level = quality_level(fact, 0, 0)
        reasons = sorted(set(birth_reasons + event_reasons))
        max_report_level, allowed, blocked = module_policy(level, reasons)
        overall = round(b_score * 0.6 + e_score * 0.3 + s_score * 0.1)
        subject_id = fact["subject_id"]
        conn.execute(
            """
            INSERT OR REPLACE INTO data_quality_assessments (
              assessment_id, subject_type, subject_id, birth_score, event_score,
              source_score, overall_score, quality_level, max_report_level,
              allowed_modules_json, blocked_modules_json, reason_codes_json,
              assessed_at
            ) VALUES (?, 'local_person', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                f"DQA_LOCAL_{subject_id}", subject_id, b_score, e_score, s_score,
                overall, level, max_report_level, dump(allowed), dump(blocked), dump(reasons),
            ),
        )
        levels[level] += 1
    return len(rows), levels


def run(db_path: Path) -> dict[str, Any]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        migrate(conn)
        public_count, public_levels, report_levels = assess_public_people(conn)
        local_count, local_levels = assess_local_people(conn)
        split_counts = dict(conn.execute("SELECT dataset_split, COUNT(*) FROM validation_assignments GROUP BY dataset_split").fetchall())
        conn.commit()
        return {
            "database": str(db_path),
            "quality_model_version": QUALITY_VERSION,
            "public_people_assessed": public_count,
            "local_people_assessed": local_count,
            "public_quality_levels": dict(sorted(public_levels.items())),
            "local_quality_levels": dict(sorted(local_levels.items())),
            "report_readiness": dict(sorted(report_levels.items())),
            "validation_splits": split_counts,
        }
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Build strict data quality scores and deterministic validation splits.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    print(json.dumps(run(args.db), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
