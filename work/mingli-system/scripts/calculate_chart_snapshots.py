from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from lunar_python import Solar

from time_calibration import true_solar_time


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "mingli_validation.db"
ENGINE_VERSION = "eightchar-v2"

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

BRANCH_MIDPOINT_HOURS = {
    "子": 0,
    "丑": 2,
    "寅": 4,
    "卯": 6,
    "辰": 8,
    "巳": 10,
    "午": 12,
    "未": 14,
    "申": 16,
    "酉": 18,
    "戌": 20,
    "亥": 22,
}

STEM_COMBINATIONS = {frozenset(pair) for pair in ("甲己", "乙庚", "丙辛", "丁壬", "戊癸")}
BRANCH_COMBINATIONS = {frozenset(pair) for pair in ("子丑", "寅亥", "卯戌", "辰酉", "巳申", "午未")}
BRANCH_CLASHES = {frozenset(pair) for pair in ("子午", "丑未", "寅申", "卯酉", "辰戌", "巳亥")}
THREE_HARMONIES = {frozenset(group) for group in ("申子辰", "亥卯未", "寅午戌", "巳酉丑")}


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


def parse_time(value: str | None, precision: str) -> tuple[int, int] | None:
    if not value or precision not in {"exact", "approximate"}:
        return None
    match = re.search(r"(?<!\d)([01]?\d|2[0-3])(?::|点)([0-5]?\d)?", value)
    if match:
        return int(match.group(1)), int(match.group(2) or 0)
    for branch, hour in BRANCH_MIDPOINT_HOURS.items():
        if branch in value:
            return hour, 0
    return None


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


def relation_tags(stems: list[str], branches: list[str]) -> list[str]:
    tags: set[str] = set()
    for index, left in enumerate(stems):
        for right in stems[index + 1:]:
            if frozenset((left, right)) in STEM_COMBINATIONS:
                tags.add(f"天干合:{left}{right}")
    for index, left in enumerate(branches):
        for right in branches[index + 1:]:
            pair = frozenset((left, right))
            if pair in BRANCH_COMBINATIONS:
                tags.add(f"地支六合:{left}{right}")
            if pair in BRANCH_CLASHES:
                tags.add(f"地支六冲:{left}{right}")
    branch_set = set(branches)
    for group in THREE_HARMONIES:
        if group.issubset(branch_set):
            tags.add(f"地支三合:{''.join(sorted(group))}")
    return sorted(tags)


def calculate_chart(date_text: str, time_text: str | None, time_precision: str) -> dict[str, Any] | None:
    parts = parse_date(date_text)
    if not parts:
        return None
    year, month, day = parts
    parsed_time = parse_time(time_text, time_precision)
    hour, minute = parsed_time or (12, 0)
    eight_char = Solar.fromYmdHms(year, month, day, hour, minute, 0).getLunar().getEightChar()
    year_pillar = eight_char.getYear()
    month_pillar = eight_char.getMonth()
    day_pillar = eight_char.getDay()
    hour_pillar = eight_char.getTime() if parsed_time else None
    branch = month_branch(month_pillar)
    pillars = [year_pillar, month_pillar, day_pillar] + ([hour_pillar] if hour_pillar else [])
    stems = [pillar[0] for pillar in pillars]
    branches = [pillar[1] for pillar in pillars]
    ten_god_tags: list[dict[str, Any]] = [
        {"pillar": "year", "stem": eight_char.getYearShiShenGan(), "branches": eight_char.getYearShiShenZhi()},
        {"pillar": "month", "stem": eight_char.getMonthShiShenGan(), "branches": eight_char.getMonthShiShenZhi()},
        {"pillar": "day", "stem": "日主", "branches": eight_char.getDayShiShenZhi()},
    ]
    details: dict[str, Any] = {
        "hidden_stems": {
            "year": eight_char.getYearHideGan(),
            "month": eight_char.getMonthHideGan(),
            "day": eight_char.getDayHideGan(),
        },
        "five_elements": {
            "year": eight_char.getYearWuXing(),
            "month": eight_char.getMonthWuXing(),
            "day": eight_char.getDayWuXing(),
        },
        "na_yin": {
            "year": eight_char.getYearNaYin(),
            "month": eight_char.getMonthNaYin(),
            "day": eight_char.getDayNaYin(),
        },
        "tai_yuan": eight_char.getTaiYuan(),
    }
    if hour_pillar:
        ten_god_tags.append({"pillar": "hour", "stem": eight_char.getTimeShiShenGan(), "branches": eight_char.getTimeShiShenZhi()})
        details["hidden_stems"]["hour"] = eight_char.getTimeHideGan()
        details["five_elements"]["hour"] = eight_char.getTimeWuXing()
        details["na_yin"]["hour"] = eight_char.getTimeNaYin()
        details["ming_gong"] = eight_char.getMingGong()
        details["shen_gong"] = eight_char.getShenGong()
    return {
        "year_pillar": year_pillar,
        "month_pillar": month_pillar,
        "day_pillar": day_pillar,
        "hour_pillar": hour_pillar,
        "day_master": day_master(day_pillar),
        "month_command": branch,
        "climate_tags": MONTH_CLIMATE.get(branch or "", []),
        "ten_god_tags": ten_god_tags,
        "conflict_combination_tags": relation_tags(stems, branches),
        "details": details,
    }


def confidence_for(subject_type: str, time_precision: str, date_precision: str, year: int) -> str:
    if date_precision != "day":
        return "D"
    if year < 1582:
        return "D"
    if time_precision in {"exact", "approximate"}:
        return "B"
    if subject_type == "public_person":
        return "C"
    return "C"


def upsert_snapshot(conn: sqlite3.Connection, fact: sqlite3.Row) -> bool:
    chart = calculate_chart(fact["date_standard"], fact["time_text"], fact["time_precision"])
    if not chart:
        return False
    snapshot_id = f"CHART_{fact['birth_fact_id']}"
    year = parse_date(fact["date_standard"])[0]
    confidence = confidence_for(fact["subject_type"], fact["time_precision"], fact["date_precision"], year)
    boundary_flags: list[str] = []
    if year < 1582:
        boundary_flags.append("HISTORICAL_CALENDAR_PRE_1582")
    if fact["time_precision"] == "unknown":
        boundary_flags.append("TIME_UNKNOWN")
    if fact["time_precision"] == "boundary":
        boundary_flags.append("TIME_BRANCH_BOUNDARY")
    if fact["longitude"] is None or not fact["timezone"]:
        boundary_flags.append("TRUE_SOLAR_TIME_NOT_CALCULATED")
    parsed_time = parse_time(fact["time_text"], fact["time_precision"])
    if fact["time_precision"] == "approximate":
        boundary_flags.append("TIME_APPROXIMATE")
    if parsed_time and parsed_time[0] == 23:
        boundary_flags.append("ZI_HOUR_DAY_BOUNDARY_DISPUTED")

    if parsed_time and fact["longitude"] is not None and fact["timezone"]:
        hour, minute = parsed_time
        local_clock = datetime(year, parse_date(fact["date_standard"])[1], parse_date(fact["date_standard"])[2], hour, minute)
        try:
            solar_clock, correction_minutes = true_solar_time(local_clock, float(fact["longitude"]), fact["timezone"])
            solar_chart = calculate_chart(solar_clock.strftime("%Y-%m-%d"), solar_clock.strftime("%H:%M"), "exact")
            chart["details"]["true_solar_time"] = {
                "local_clock": local_clock.isoformat(timespec="minutes"),
                "apparent_solar_clock": solar_clock.isoformat(timespec="minutes"),
                "correction_minutes": round(correction_minutes, 2),
                "longitude": fact["longitude"],
                "timezone": fact["timezone"],
                "pillars": {
                    "year": solar_chart["year_pillar"],
                    "month": solar_chart["month_pillar"],
                    "day": solar_chart["day_pillar"],
                    "hour": solar_chart["hour_pillar"],
                } if solar_chart else None,
            }
            if solar_chart and solar_chart["hour_pillar"] != chart["hour_pillar"]:
                boundary_flags.append("TRUE_SOLAR_TIME_CHANGES_HOUR_PILLAR")
        except ValueError:
            boundary_flags.append("TIMEZONE_CALIBRATION_FAILED")
    calculation_level = "four_pillars_local_clock" if chart["hour_pillar"] else "three_pillars"
    if chart["details"].get("true_solar_time"):
        calculation_level = "four_pillars_true_solar_checked"
    if fact["time_precision"] == "boundary":
        calculation_level = "three_pillars_boundary"
    conn.execute(
        """
        INSERT OR REPLACE INTO chart_snapshots (
          chart_snapshot_id, subject_type, subject_id, calculation_level,
          year_pillar, month_pillar, day_pillar, hour_pillar, day_master,
          month_command, climate_tags_json, ten_god_tags_json,
          conflict_combination_tags_json, details_json, boundary_flags_json,
          engine_version, confidence, calculation_notes,
          updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            snapshot_id,
            fact["subject_type"],
            fact["subject_id"],
            calculation_level,
            chart["year_pillar"],
            chart["month_pillar"],
            chart["day_pillar"],
            chart["hour_pillar"],
            chart["day_master"],
            chart["month_command"],
            dump(chart["climate_tags"]),
            dump(chart["ten_god_tags"]),
            dump(chart["conflict_combination_tags"]),
            dump(chart["details"]),
            dump(boundary_flags),
            ENGINE_VERSION,
            confidence,
            "Calculated with lunar_python EightChar. When coordinates and an IANA time zone are present, the local-clock chart is retained and an apparent-solar-time alternative is stored for comparison.",
        ),
    )
    return True


def run(db_path: Path) -> dict[str, Any]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(chart_snapshots)")}
        for name, definition in (
            ("details_json", "TEXT NOT NULL DEFAULT '{}'"),
            ("boundary_flags_json", "TEXT NOT NULL DEFAULT '[]'"),
            ("engine_version", "TEXT NOT NULL DEFAULT 'legacy'"),
        ):
            if name not in columns:
                conn.execute(f"ALTER TABLE chart_snapshots ADD COLUMN {name} {definition}")
        facts = conn.execute(
            """
            SELECT birth_fact_id, subject_type, subject_id, date_standard,
                   date_precision, time_precision, time_text, longitude,
                   latitude, timezone
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
