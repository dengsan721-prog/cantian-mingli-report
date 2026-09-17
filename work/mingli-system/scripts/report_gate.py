from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

from init_database import DEFAULT_DB


REPORT_MODEL_VERSION = "precision-gate-v1"


def load_assessment(conn: sqlite3.Connection, subject_type: str, subject_id: str) -> sqlite3.Row | None:
    conn.row_factory = sqlite3.Row
    return conn.execute(
        """
        SELECT *
        FROM data_quality_assessments
        WHERE subject_type = ? AND subject_id = ?
        """,
        (subject_type, subject_id),
    ).fetchone()


def gate_decision(assessment: sqlite3.Row | None, requested_modules: list[str]) -> dict[str, Any]:
    if assessment is None:
        return {
            "decision": "block",
            "reason": "QUALITY_ASSESSMENT_MISSING",
            "max_report_level": "intake_only",
            "allowed_modules": [],
            "blocked_requested_modules": sorted(set(requested_modules)),
            "required_actions": ["Run build_precision_foundation.py after recording the birth facts."],
        }

    allowed = set(json.loads(assessment["allowed_modules_json"]))
    globally_blocked = set(json.loads(assessment["blocked_modules_json"]))
    requested = set(requested_modules)
    blocked_requested = sorted(requested - allowed)
    allowed_requested = sorted(requested & allowed)
    max_report_level = assessment["max_report_level"]

    if max_report_level == "intake_only":
        decision = "block"
    elif blocked_requested:
        decision = "degrade"
    else:
        decision = "allow"

    reason_codes = json.loads(assessment["reason_codes_json"])
    required_actions: list[str] = []
    if "DATE_NOT_DAY_PRECISION" in reason_codes:
        required_actions.append("Obtain and source a complete birth date.")
    if "TIME_UNKNOWN_OR_UNRELIABLE" in reason_codes:
        required_actions.append("Obtain a reliable birth time before hour-pillar or precise-timing analysis.")
    if "TIME_APPROXIMATE" in reason_codes:
        required_actions.append("Narrow the approximate birth time before precise-timing analysis.")
    if "PLACE_MISSING" in reason_codes:
        required_actions.append("Obtain the birth place before location-sensitive calibration.")
    if "COORDINATES_MISSING" in reason_codes or "TIMEZONE_MISSING" in reason_codes:
        required_actions.append("Geocode the birth place and resolve its historical time zone.")
    if "HISTORICAL_CALENDAR_CONVERSION_REQUIRED" in reason_codes:
        required_actions.append("Resolve the historical calendar convention before date-sensitive claims.")
    if "CALENDAR_NOT_VERIFIED" in reason_codes:
        required_actions.append("Verify the source calendar and its conversion to the standard date.")
    if "HISTORICAL_TIME_STANDARD_NOT_VERIFIED" in reason_codes:
        required_actions.append("Verify the legal clock standard and daylight-saving rules at birth.")
    if "FEWER_THAN_FIVE_EVENTS" in reason_codes or "FEWER_THAN_THREE_EVENT_TYPES" in reason_codes:
        required_actions.append("Collect at least five dated events across three event types for calibration.")

    return {
        "decision": decision,
        "quality_level": assessment["quality_level"],
        "quality_scores": {
            "birth": assessment["birth_score"],
            "events": assessment["event_score"],
            "sources": assessment["source_score"],
            "overall": assessment["overall_score"],
        },
        "max_report_level": max_report_level,
        "allowed_requested_modules": allowed_requested,
        "blocked_requested_modules": blocked_requested,
        "all_allowed_modules": sorted(allowed),
        "all_blocked_modules": sorted(globally_blocked),
        "reason_codes": reason_codes,
        "required_actions": required_actions,
        "mandatory_disclosure": (
            "This gate controls data sufficiency and claim scope. It does not establish scientific "
            "validity or guarantee that a traditional interpretation predicts an outcome."
        ),
    }


def run(db_path: Path, subject_type: str, subject_id: str, requested_modules: list[str]) -> dict[str, Any]:
    conn = sqlite3.connect(db_path)
    try:
        decision = gate_decision(load_assessment(conn, subject_type, subject_id), requested_modules)
        return {
            "model_version": REPORT_MODEL_VERSION,
            "subject_type": subject_type,
            "subject_id": subject_id,
            "requested_modules": sorted(set(requested_modules)),
            **decision,
        }
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Check whether requested report modules are supported by the available evidence.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--subject-type", choices=("local_person", "public_person"), required=True)
    parser.add_argument("--subject-id", required=True)
    parser.add_argument("--module", action="append", default=[])
    args = parser.parse_args()
    result = run(args.db, args.subject_type, args.subject_id, args.module)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(2 if result["decision"] == "block" else 0)


if __name__ == "__main__":
    main()
