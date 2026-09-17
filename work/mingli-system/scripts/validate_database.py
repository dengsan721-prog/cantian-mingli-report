from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "mingli_validation.db"

REQUIRED_TABLES = [
    "source_registry",
    "theory_sources",
    "knowledge_rules",
    "local_persons",
    "public_persons",
    "birth_facts",
    "life_events_public",
    "chart_snapshots",
    "case_studies",
    "correction_records",
    "rule_evaluations",
    "bias_matrices",
    "data_quality_assessments",
    "validation_assignments",
    "validation_metrics",
    "validation_protocols",
    "rectification_models",
    "birth_time_rectification_runs",
    "rectification_event_partitions",
    "rectification_candidates",
    "rectification_benchmarks",
    "report_runs",
    "report_claims",
    "import_batches",
]

JSON_COLUMNS = {
    "source_registry": ["allowed_fields_json", "forbidden_fields_json"],
    "knowledge_rules": ["source_ids_json", "applicable_conditions_json", "forbidden_conditions_json"],
    "local_persons": ["birthplace_json", "known_chart_json"],
    "public_persons": ["external_ids_json", "aliases_json", "language_labels_json", "occupations_json", "fields_json", "countries_json", "source_ids_json"],
    "birth_facts": ["place_standard_json"],
    "chart_snapshots": ["climate_tags_json", "ten_god_tags_json", "conflict_combination_tags_json", "details_json", "boundary_flags_json"],
    "case_studies": ["chart_snapshot_json", "model_tags_json", "report_ids_json", "known_life_events_json", "lessons_json", "similarity_keys_json"],
    "data_quality_assessments": ["allowed_modules_json", "blocked_modules_json", "reason_codes_json"],
    "validation_metrics": ["confidence_interval_json"],
    "validation_protocols": ["cohort_definition_json", "target_event_types_json", "forecast_window_json", "baseline_spec_json"],
    "rectification_models": ["scoring_spec_json"],
    "birth_time_rectification_runs": ["reason_codes_json", "leakage_audit_json"],
    "rectification_candidates": ["chart_json", "supporting_event_ids_json", "opposing_event_ids_json"],
    "report_claims": ["rule_ids_json", "evidence_ids_json"],
}

REQUIRED_COLUMNS = {
    "birth_facts": {"calendar_model", "calendar_verification_status", "time_standard_status"},
    "chart_snapshots": {"details_json", "boundary_flags_json", "engine_version"},
    "public_persons": {"gender"},
    "validation_assignments": {"era_bucket"},
}

REQUIRED_TRIGGERS = {
    "trg_rectification_model_validation_insert",
    "trg_rectification_model_validation_update",
    "trg_rectification_selection_insert",
    "trg_rectification_selection_update",
}


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name = ?",
        (table,),
    ).fetchone() is not None


def validate_json_columns(conn: sqlite3.Connection) -> list[str]:
    errors: list[str] = []
    for table, columns in JSON_COLUMNS.items():
        for column in columns:
            for rowid, value in conn.execute(f"SELECT rowid, {column} FROM {table}"):
                try:
                    json.loads(value or "{}")
                except Exception as exc:
                    errors.append(f"{table}.{column} rowid={rowid}: {exc}")
    return errors


def validate_required_columns(conn: sqlite3.Connection) -> list[str]:
    errors: list[str] = []
    for table, required in REQUIRED_COLUMNS.items():
        actual = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for column in sorted(required - actual):
            errors.append(f"{table}.{column} is missing")
    return errors


def validate_required_triggers(conn: sqlite3.Connection) -> list[str]:
    actual = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")}
    return [f"trigger {name} is missing" for name in sorted(REQUIRED_TRIGGERS - actual)]


def validate(db_path: Path) -> dict[str, object]:
    conn = sqlite3.connect(db_path)
    try:
        missing = [table for table in REQUIRED_TABLES if not table_exists(conn, table)]
        json_errors = validate_json_columns(conn) if not missing else []
        column_errors = validate_required_columns(conn) if not missing else []
        trigger_errors = validate_required_triggers(conn) if not missing else []
        foreign_key_errors = [list(row) for row in conn.execute("PRAGMA foreign_key_check").fetchall()]
        return {
            "database": str(db_path),
            "ok": not missing and not json_errors and not column_errors and not trigger_errors and not foreign_key_errors,
            "missing_tables": missing,
            "column_errors": column_errors,
            "trigger_errors": trigger_errors,
            "json_errors": json_errors[:50],
            "json_error_count": len(json_errors),
            "foreign_key_errors": foreign_key_errors[:50],
            "foreign_key_error_count": len(foreign_key_errors),
        }
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Mingli database structure and JSON fields.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    result = validate(args.db)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
