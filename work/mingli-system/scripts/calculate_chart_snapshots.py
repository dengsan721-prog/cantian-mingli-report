from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from lunar_python import Solar


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "mingli_validation.db"

STEM_ELEMENTS = {
    "甲": "木",
    "乙": "木",
    "丙": "火",
    "丁": "火",
    "戊": "土",
    "己": "土",
    "庚": "金",
    "辛": "金",
    "壬": "水",
    "癸": "水",
}

MONTH_CLIMATE = {
    "寅": ["春木", "生发"],
    "卯": ["春木", "旺木"],
    "辰": ["湿土", "春末"],
    "巳": ["夏火", "初热"],
    "午": ["夏火", "炎上"],
    "未": ["燥土", "夏末"],
    "申": ["秋金", "初肃"],
    "酉": ["秋金", "金旺"],
    "戌": ["燥土", "秋末"],
    "亥": ["冬水", "寒水"],
    "子": ["冬水", "水旺"],
    "丑": ["寒土", "冬末"],
}


def dump(value: Any) -> str:
    return json.dumps(value if value is not None else [], ensure_ascii=False)


def parse_date(value: str | None) -> tuple[int, int, int] | None:
    if not value:
        return None
    match = re.match(r"^(\d{1,4})-(\d{2})-(\d{2})$", value)
    if not match:
        return None
    year, month, day = (int(part) for part in match.groups())
    if month <= 0 or day <= 0:
        return None
    return year, month, day


def month_branch(month_pillar: str | None) -> str | None:
    if not month_pillar or len(month_pillar) < 2:
        return None
    return month_pillar[1]


def day_master(day_pillar: str | None) -> str | None:
    if not day_pillar:
        return None
    stem = day_pillar[0]
    element = STEM_ELEMENTS.get(stem, "")
    return f"{stem}{element}" if element else stem


def calculate_three_pillars(date_text: str) -> dict[str, Any] | None:
    parts = parse_date(date_text)
    if not parts:
        return None
    year, month, day = parts
    lunar = Solar.fromYmd(year, month, day).getLunar()
    year_pillar = lunar.getYearInGanZhi()
    month_pillar = lunar.getMonthInGanZhi()
    day_pillar = lunar.getDayInGanZhi()
    branch = month_branch(month_pillar)
    return {
        "year_pillar": year_pillar,
        "month_pillar": month_pillar,
        "day_pillar": day_pillar,
        "hour_pillar": None,
        "day_master": day_master(day_pillar),
        "month_command": branch,
        "climate_tags": MONTH_CLIMATE.get(branch or "", []),
        "ten_god_tags": [],
        "conflict_combination_tags": [],
    }


def confidence_for(subject_type: str, time_precision: str, date_precision: str) -> str:
    if date_precision != "day":
        return "D"
    if time_precision in {"exact", "approximate"}:
        return "B"
    if subject_type == "public_person":
        return "C"
    return "C"


def upsert_snapshot(conn: sqlite3.Connection, fact: sqlite3.Row) -> bool:
    chart = calculate_three_pillars(fact["date_standard"])
    if not chart:
        return False
    snapshot_id = f"CHART_{fact['birth_fact_id']}"
    confidence = confidence_for(fact["subject_type"], fact["time_precision"], fact["date_precision"])
    conn.execute(
        """
        INSERT OR REPLACE INTO chart_snapshots (
          chart_snapshot_id, subject_type, subject_id, calculation_level,
          year_pillar, month_pillar, day_pillar, hour_pillar, day_master,
          month_command, climate_tags_json, ten_god_tags_json,
          conflict_combination_tags_json, confidence, calculation_notes,
          updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            snapshot_id,
            fact["subject_type"],
            fact["subject_id"],
            "three_pillars" if fact["time_precision"] == "unknown" else "four_pillars_pending_hour",
            chart["year_pillar"],
            chart["month_pillar"],
            chart["day_pillar"],
            chart["hour_pillar"],
            chart["day_master"],
            chart["month_command"],
            dump(chart["climate_tags"]),
            dump(chart["ten_god_tags"]),
            dump(chart["conflict_combination_tags"]),
            confidence,
            "Auto-generated from birth_facts date_standard. Hour pillar not calculated in this pass.",
        ),
    )
    return True


def run(db_path: Path) -> dict[str, Any]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        facts = conn.execute(
            """
            SELECT birth_fact_id, subject_type, subject_id, date_standard,
                   date_precision, time_precision
            FROM birth_facts
            WHERE date_standard IS NOT NULL
              AND date_precision = 'day'
            """
        ).fetchall()
        upserted = 0
        skipped = 0
        for fact in facts:
            if upsert_snapshot(conn, fact):
                upserted += 1
            else:
                skipped += 1
        conn.commit()
        return {
            "db": str(db_path),
            "eligible_birth_facts": len(facts),
            "snapshots_upserted": upserted,
            "skipped": skipped,
        }
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate basic chart snapshots from birth facts.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    print(json.dumps(run(args.db), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
