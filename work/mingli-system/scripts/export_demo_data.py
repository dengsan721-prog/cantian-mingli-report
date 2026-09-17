from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "mingli_validation.db"
DEFAULT_OUTPUT = ROOT.parent / "mingli-demo" / "assets" / "mingli_database_export.js"


def load_json(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def confidence_from_time_accuracy(value: str | None) -> str:
    if value == "exact":
        return "A"
    if value in {"approximate", "boundary"}:
        return "B"
    return "C"


def local_people(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT name, gender, calendar_type, birth_year, birth_month, birth_day,
               time_text, time_accuracy, birthplace_json, known_chart_json, notes
        FROM local_persons
        ORDER BY name
        """
    ).fetchall()
    people = []
    for row in rows:
        birthplace = load_json(row["birthplace_json"], {})
        chart = load_json(row["known_chart_json"], {})
        people.append(
            {
                "name": row["name"],
                "gender": row["gender"],
                "calendarType": row["calendar_type"],
                "year": row["birth_year"],
                "month": row["birth_month"],
                "day": row["birth_day"],
                "timeText": row["time_text"] or "",
                "birthplace": birthplace.get("raw") or "",
                "chart": {
                    "solarDate": chart.get("solar_date") or "待精排",
                    "bazi": chart.get("bazi_core") or "待精排",
                    "dayMaster": chart.get("day_master") or "待精排",
                    "confidence": confidence_from_time_accuracy(row["time_accuracy"]),
                    "model": chart.get("model_name") or "待建立模型",
                    "notes": row["notes"] or "",
                },
            }
        )
    return people


def stats(conn: sqlite3.Connection) -> dict[str, Any]:
    counts = {
        row["table_name"]: row["row_count"]
        for row in conn.execute("SELECT table_name, row_count FROM v_database_counts")
    }
    quality = [dict(row) for row in conn.execute("SELECT * FROM v_public_person_quality")]
    precision = [dict(row) for row in conn.execute("SELECT * FROM v_birth_fact_precision")]
    return {"counts": counts, "publicPersonQuality": quality, "birthFactPrecision": precision}


def export(db_path: Path, output: Path) -> dict[str, Any]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        payload = {
            "version": "1.0.0",
            "sourceDatabase": str(db_path),
            "localPeople": local_people(conn),
            "stats": stats(conn),
        }
    finally:
        conn.close()

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "window.MINGLI_DATABASE_EXPORT = "
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + ";\n",
        encoding="utf-8",
    )
    return {"output": str(output), "local_people": len(payload["localPeople"])}


def main() -> None:
    parser = argparse.ArgumentParser(description="Export database records for the static demo.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(export(args.db, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
