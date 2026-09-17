from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
from pathlib import Path
from typing import Any

from build_precision_foundation import migrate
from calculate_chart_snapshots import BRANCH_MIDPOINT_HOURS, calculate_chart, parse_time
from init_database import DEFAULT_DB


METHOD_VERSION = "twelve-branch-rectification-v1"
MODEL_ID = "RECTIFICATION_MODEL_DRAFT_V1"
BRANCH_ORDER = tuple(BRANCH_MIDPOINT_HOURS)


def dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def partition_events(events: list[sqlite3.Row]) -> tuple[list[sqlite3.Row], list[sqlite3.Row]]:
    ordered = sorted(events, key=lambda row: (row["event_date"], row["event_id"]))
    if len(ordered) < 5:
        return [], []
    calibration_count = max(3, min(len(ordered) - 2, math.ceil(len(ordered) * 0.7)))
    return ordered[:calibration_count], ordered[calibration_count:]


def assignment_hash(run_id: str, event_id: str, partition_name: str) -> str:
    return hashlib.sha256(f"{METHOD_VERSION}|{run_id}|{event_id}|{partition_name}".encode("utf-8")).hexdigest()


def ensure_draft_model(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO rectification_models (
          model_id, model_version, status, scoring_spec_json,
          trained_on_split, gold_sample_size, notes
        ) VALUES (?, ?, 'draft', ?, NULL, 0, ?)
        """,
        (
            MODEL_ID,
            METHOD_VERSION,
            dump(
                {
                    "candidate_space": "twelve_traditional_double_hours",
                    "prior": "uniform",
                    "event_partition": "chronological_70_30_with_two_event_holdout",
                    "scoring": "disabled_until_known-time blind validation",
                }
            ),
            "Candidate generation only. It must not select a birth hour until a separately validated scoring model is installed.",
        ),
    )


def branches_are_adjacent(left: str, right: str) -> bool:
    left_index = BRANCH_ORDER.index(left)
    right_index = BRANCH_ORDER.index(right)
    return min((left_index - right_index) % 12, (right_index - left_index) % 12) == 1


def eligible_people(conn: sqlite3.Connection, limit: int | None, benchmark_known: bool) -> list[sqlite3.Row]:
    time_filter = "bf.time_precision = 'exact'" if benchmark_known else "bf.time_precision IN ('unknown', 'boundary')"
    sql = """
        SELECT pp.public_person_id, bf.birth_fact_id, bf.date_standard,
               bf.time_text, bf.time_precision,
               bf.longitude, bf.latitude, bf.timezone,
               dqa.reason_codes_json,
               COUNT(DISTINCT le.event_id) AS dated_event_count,
               COUNT(DISTINCT le.event_type) AS event_type_count
        FROM public_persons pp
        JOIN birth_facts bf
          ON bf.subject_type = 'public_person' AND bf.subject_id = pp.public_person_id
        JOIN data_quality_assessments dqa
          ON dqa.subject_type = 'public_person' AND dqa.subject_id = pp.public_person_id
        JOIN life_events_public le
          ON le.public_person_id = pp.public_person_id
         AND le.allowed_for_modeling = 1
         AND le.event_date IS NOT NULL
         AND le.event_precision != 'unknown'
        WHERE bf.date_precision = 'day'
          AND {time_filter}
        GROUP BY pp.public_person_id, bf.birth_fact_id
        HAVING dated_event_count >= 5 AND event_type_count >= 3
        ORDER BY pp.public_person_id
    """.format(time_filter=time_filter)
    params: tuple[Any, ...] = ()
    if limit is not None:
        sql += " LIMIT ?"
        params = (limit,)
    return conn.execute(sql, params).fetchall()


def person_events(conn: sqlite3.Connection, public_person_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT event_id, event_type, event_date, event_precision, confidence
        FROM life_events_public
        WHERE public_person_id = ?
          AND allowed_for_modeling = 1
          AND event_date IS NOT NULL
          AND event_precision != 'unknown'
        ORDER BY event_date, event_id
        """,
        (public_person_id,),
    ).fetchall()


def chart_summary(chart: dict[str, Any]) -> dict[str, Any]:
    return {
        "year_pillar": chart["year_pillar"],
        "month_pillar": chart["month_pillar"],
        "day_pillar": chart["day_pillar"],
        "hour_pillar": chart["hour_pillar"],
        "day_master": chart["day_master"],
        "ten_god_tags": chart["ten_god_tags"],
        "relation_tags": chart["conflict_combination_tags"],
        "hypothesis_basis": "traditional_double_hour_branch_midpoint",
    }


def known_hour_branch(person: sqlite3.Row) -> str | None:
    parsed = parse_time(person["time_text"], person["time_precision"])
    if parsed is None:
        return None
    hour, minute = parsed
    chart = calculate_chart(person["date_standard"], f"{hour:02d}:{minute:02d}", "exact")
    hour_pillar = chart["hour_pillar"] if chart else None
    return hour_pillar[1] if hour_pillar else None


def build_run(conn: sqlite3.Connection, person: sqlite3.Row, benchmark_known: bool) -> bool:
    events = person_events(conn, person["public_person_id"])
    calibration, holdout = partition_events(events)
    if not calibration or not holdout:
        return False

    run_id = f"RECT_{person['public_person_id']}_{METHOD_VERSION}"
    conn.execute("DELETE FROM rectification_event_partitions WHERE run_id = ?", (run_id,))
    conn.execute("DELETE FROM rectification_candidates WHERE run_id = ?", (run_id,))
    conn.execute("DELETE FROM rectification_benchmarks WHERE run_id = ?", (run_id,))
    conn.execute("DELETE FROM birth_time_rectification_runs WHERE run_id = ?", (run_id,))

    reasons = set(json.loads(person["reason_codes_json"] or "[]"))
    reasons.update({"NO_VALIDATED_RECTIFICATION_MODEL", "CANDIDATES_ARE_NOT_VERIFIED_BIRTH_TIMES"})
    if not person["timezone"]:
        reasons.add("HISTORICAL_TIME_STANDARD_NOT_VERIFIED")
    leakage_audit = {
        "partition_policy": "chronological",
        "calibration_event_ids": [row["event_id"] for row in calibration],
        "holdout_event_ids": [row["event_id"] for row in holdout],
        "overlap_count": 0,
        "holdout_used_for_candidate_scoring": False,
        "known_time_hidden": benchmark_known,
    }
    conn.execute(
        """
        INSERT INTO birth_time_rectification_runs (
          run_id, subject_type, subject_id, birth_fact_id, model_id,
          method_version, status, event_count, calibration_event_count,
          holdout_event_count, selected_branch, selected_probability,
          probability_margin, normalized_entropy, reason_codes_json,
          leakage_audit_json
        ) VALUES (?, 'public_person', ?, ?, ?, ?, 'not_evaluable', ?, ?, ?, NULL, NULL, NULL, 1.0, ?, ?)
        """,
        (
            run_id,
            person["public_person_id"],
            person["birth_fact_id"],
            MODEL_ID,
            METHOD_VERSION,
            len(events),
            len(calibration),
            len(holdout),
            dump(sorted(reasons)),
            dump(leakage_audit),
        ),
    )

    for partition_name, partition in (("calibration", calibration), ("holdout", holdout)):
        for ordinal, event in enumerate(partition, start=1):
            conn.execute(
                """
                INSERT INTO rectification_event_partitions (
                  run_id, event_id, partition_name, event_ordinal, assignment_hash
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    event["event_id"],
                    partition_name,
                    ordinal,
                    assignment_hash(run_id, event["event_id"], partition_name),
                ),
            )

    uniform_probability = 1 / len(BRANCH_ORDER)
    for branch in BRANCH_ORDER:
        hour = BRANCH_MIDPOINT_HOURS[branch]
        representative_time = f"{hour:02d}:00"
        chart = calculate_chart(person["date_standard"], representative_time, "exact")
        if chart is None:
            continue
        conn.execute(
            """
            INSERT INTO rectification_candidates (
              candidate_id, run_id, hour_branch, representative_time,
              hour_pillar, chart_json, prior_probability, raw_score,
              posterior_probability, candidate_rank, supporting_event_ids_json,
              opposing_event_ids_json, candidate_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, NULL, '[]', '[]', 'unscored')
            """,
            (
                f"{run_id}_{branch}",
                run_id,
                branch,
                representative_time,
                chart["hour_pillar"],
                dump(chart_summary(chart)),
                uniform_probability,
                uniform_probability,
            ),
        )
    if benchmark_known:
        actual_branch = known_hour_branch(person)
        if actual_branch:
            conn.execute(
                """
                INSERT INTO rectification_benchmarks (
                  benchmark_id, run_id, known_hour_branch, predicted_hour_branch,
                  exact_match, adjacent_match, hidden_time_policy, evaluation_split
                ) VALUES (?, ?, ?, NULL, NULL, NULL, ?, 'unassigned')
                """,
                (
                    f"BENCH_{run_id}",
                    run_id,
                    actual_branch,
                    "Birth time excluded from candidate generation and unavailable to a future scorer until prediction is frozen.",
                ),
            )
    return True


def run(db_path: Path, limit: int | None, benchmark_known: bool = False) -> dict[str, Any]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        migrate(conn)
        ensure_draft_model(conn)
        people = eligible_people(conn, limit, benchmark_known)
        created = sum(1 for person in people if build_run(conn, person, benchmark_known))
        conn.commit()
        candidate_count = conn.execute(
            "SELECT COUNT(*) FROM rectification_candidates WHERE run_id LIKE ?",
            (f"%_{METHOD_VERSION}",),
        ).fetchone()[0]
        return {
            "database": str(db_path),
            "method_version": METHOD_VERSION,
            "eligible_people": len(people),
            "runs_created": created,
            "candidates_present": candidate_count,
            "benchmark_mode": benchmark_known,
            "benchmarks_present": conn.execute("SELECT COUNT(*) FROM rectification_benchmarks").fetchone()[0],
            "selection_status": "disabled_until_validated_model",
        }
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate auditable twelve-branch birth-time rectification candidates.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--benchmark-known", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.db, args.limit, args.benchmark_known), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
