from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "mingli_validation.db"


def rows(conn: sqlite3.Connection, sql: str) -> list[dict[str, object]]:
    conn.row_factory = sqlite3.Row
    return [dict(row) for row in conn.execute(sql).fetchall()]


def collect(db_path: Path) -> dict[str, object]:
    conn = sqlite3.connect(db_path)
    try:
        return {
            "database": str(db_path),
            "counts": rows(conn, "SELECT * FROM v_database_counts"),
            "public_person_quality": rows(conn, "SELECT * FROM v_public_person_quality"),
            "birth_fact_precision": rows(conn, "SELECT * FROM v_birth_fact_precision"),
            "report_readiness": rows(conn, "SELECT * FROM v_report_readiness"),
            "validation_splits": rows(conn, "SELECT * FROM v_validation_split_counts"),
            "validation_metrics": rows(conn, "SELECT * FROM validation_metrics ORDER BY metric_type, dataset_split"),
            "validation_protocols": rows(conn, "SELECT * FROM validation_protocols ORDER BY protocol_type, protocol_id"),
            "rule_confidence": rows(conn, "SELECT * FROM v_rule_confidence"),
            "recent_import_batches": rows(conn, "SELECT * FROM v_recent_import_batches LIMIT 5"),
        }
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Print Mingli database statistics.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    print(json.dumps(collect(args.db), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
