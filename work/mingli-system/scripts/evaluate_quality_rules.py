from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "mingli_validation.db"


def dump(value: Any) -> str:
    return json.dumps(value if value is not None else [], ensure_ascii=False)


def evaluate_no_hour_rule(conn: sqlite3.Connection) -> int:
    rule_id = "KR_002_NO_HOUR_NO_FULL_DETAIL"
    rows = conn.execute(
        """
        SELECT
          pp.public_person_id,
          cs.chart_snapshot_id,
          cs.calculation_level,
          cs.hour_pillar,
          cs.confidence
        FROM public_persons pp
        JOIN chart_snapshots cs
          ON cs.subject_type = 'public_person'
         AND cs.subject_id = pp.public_person_id
        """
    ).fetchall()
    count = 0
    for public_person_id, chart_snapshot_id, calculation_level, hour_pillar, confidence in rows:
        if hour_pillar is None and calculation_level == "three_pillars" and confidence in {"C", "D"}:
            match_level = "hit"
            mismatch_reason = None
        elif hour_pillar is None:
            match_level = "partial_hit"
            mismatch_reason = "Hour pillar missing, but calculation level or confidence did not fully reflect downgrade."
        else:
            match_level = "miss"
            mismatch_reason = "Hour pillar exists for public seed without time precision."
        conn.execute(
            """
            INSERT OR REPLACE INTO rule_evaluations (
              evaluation_id, rule_id, public_person_id, chart_snapshot_id,
              expected_pattern, observed_events_json, match_level,
              mismatch_reason, confidence, review_method
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"EVAL_{rule_id}_{public_person_id}",
                rule_id,
                public_person_id,
                chart_snapshot_id,
                "No-hour public sample must be downgraded to three-pillar or non-fine-grained validation.",
                dump([]),
                match_level,
                mismatch_reason,
                "high",
                "automatic",
            ),
        )
        count += 1
    return count


def rebuild_bias_matrices(conn: sqlite3.Connection) -> int:
    rules = conn.execute("SELECT DISTINCT rule_id FROM rule_evaluations").fetchall()
    count = 0
    for (rule_id,) in rules:
        rows = conn.execute(
            """
            SELECT match_level, COUNT(*) AS n
            FROM rule_evaluations
            WHERE rule_id = ?
            GROUP BY match_level
            """,
            (rule_id,),
        ).fetchall()
        totals = {level: n for level, n in rows}
        sample_size = sum(totals.values())
        if sample_size == 0:
            continue
        def rate(level: str) -> float:
            return round(totals.get(level, 0) / sample_size, 6)

        stable_conditions = []
        failure_conditions = []
        if rate("hit") >= 0.8:
            stable_conditions.append("Current data pipeline correctly downgrades no-hour public samples.")
        if rate("miss") > 0:
            failure_conditions.append("Some no-hour samples were treated as fine-grained charts.")

        conn.execute(
            """
            INSERT OR REPLACE INTO bias_matrices (
              matrix_id, rule_id, sample_size, hit_rate, partial_hit_rate,
              miss_rate, reverse_hit_rate, not_enough_data_rate,
              stable_conditions_json, failure_conditions_json,
              recommended_report_policy, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                f"MATRIX_{rule_id}",
                rule_id,
                sample_size,
                rate("hit"),
                rate("partial_hit"),
                rate("miss"),
                rate("reverse_hit"),
                rate("not_enough_data"),
                dump(stable_conditions),
                dump(failure_conditions),
                "Keep no-hour downgrade mandatory. Do not generate hour-pillar, children, late-life, or precise timing claims from public samples without birth time.",
            ),
        )
        count += 1
    return count


def run(db_path: Path) -> dict[str, Any]:
    conn = sqlite3.connect(db_path)
    try:
        eval_count = evaluate_no_hour_rule(conn)
        matrix_count = rebuild_bias_matrices(conn)
        conn.commit()
        return {
            "db": str(db_path),
            "rule_evaluations_upserted": eval_count,
            "bias_matrices_upserted": matrix_count,
        }
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate initial quality rules and rebuild bias matrices.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    print(json.dumps(run(args.db), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

