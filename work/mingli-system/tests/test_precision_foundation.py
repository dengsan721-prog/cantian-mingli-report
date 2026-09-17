from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from build_precision_foundation import era_bucket, module_policy, quality_level, split_for  # noqa: E402
from calculate_chart_snapshots import calculate_chart, relation_tags  # noqa: E402
from evaluate_quality_rules import wilson_interval  # noqa: E402
from enrich_wikidata_birthplaces import coordinate  # noqa: E402
from export_demo_data import confidence_from_quality  # noqa: E402
from import_wikidata_entities import structured_event_id  # noqa: E402
from report_gate import gate_decision  # noqa: E402
from rectify_birth_time import BRANCH_ORDER, assignment_hash, branches_are_adjacent, partition_events  # noqa: E402
from time_calibration import true_solar_time  # noqa: E402
from datetime import datetime  # noqa: E402


def fact(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "date_precision": "day",
        "calendar_verification_status": "unverified",
        "time_precision": "unknown",
        "time_standard_status": "unverified",
        "place_raw": None,
        "longitude": None,
        "latitude": None,
        "timezone": None,
    }
    value.update(overrides)
    return value


class PrecisionFoundationTests(unittest.TestCase):
    def test_quality_levels_require_real_inputs(self) -> None:
        self.assertEqual("L1", quality_level(fact(), 0, 0))
        self.assertEqual("L2", quality_level(fact(place_raw="Xi'an"), 0, 0))
        complete = fact(
            place_raw="Xi'an",
            time_precision="exact",
            longitude=108.94,
            latitude=34.34,
            timezone="Asia/Shanghai",
            calendar_verification_status="verified",
            time_standard_status="verified",
        )
        self.assertEqual("L3", quality_level(complete, 4, 3))
        self.assertEqual("L4", quality_level(complete, 5, 3))
        approximate = dict(complete, time_precision="approximate")
        self.assertEqual("L3", quality_level(approximate, 5, 3))

    def test_historical_calendar_blocks_calibration(self) -> None:
        level, allowed, blocked = module_policy("L4", ["HISTORICAL_CALENDAR_CONVERSION_REQUIRED"])
        self.assertEqual("four_pillar_provisional", level)
        self.assertNotIn("precise_timing", allowed)
        self.assertIn("outcome_rule_calibration", blocked)

    def test_split_is_deterministic(self) -> None:
        self.assertEqual(split_for("Q42"), split_for("Q42"))
        self.assertIn(split_for("Q42")[0], {"train", "validation", "test"})
        self.assertEqual("pre_1582", era_bucket("1000-01-01"))
        self.assertEqual("1950_plus", era_bucket("2018-04-05"))

    def test_wilson_interval_is_bounded(self) -> None:
        interval = wilson_interval(80, 100)
        self.assertLess(interval["low"], 0.8)
        self.assertGreater(interval["high"], 0.8)
        self.assertEqual({}, wilson_interval(0, 0))

    def test_structured_event_id_uses_statement_identity(self) -> None:
        statement = {"id": "Q42$stable-guid"}
        first = structured_event_id("Q42", "award", "Q1", statement, "2000-01-01", 0)
        second = structured_event_id("Q42", "award", "Q1", statement, "2000-01-01", 9)
        self.assertEqual(first, second)

    def test_birthplace_coordinate_extraction(self) -> None:
        entity = {
            "claims": {
                "P625": [{"mainsnak": {"datavalue": {"value": {"longitude": 108.94, "latitude": 34.34}}}}]
            }
        }
        self.assertEqual((108.94, 34.34), coordinate(entity))

    def test_demo_confidence_uses_full_quality_grade(self) -> None:
        self.assertEqual("A", confidence_from_quality("L4"))
        self.assertEqual("B", confidence_from_quality("L3"))
        self.assertEqual("D", confidence_from_quality("L1"))

    def test_rectification_partition_is_chronological_and_disjoint(self) -> None:
        events = [
            {"event_id": f"E{index}", "event_date": f"20{index:02d}-01-01"}
            for index in range(8, 0, -1)
        ]
        calibration, holdout = partition_events(events)  # type: ignore[arg-type]
        calibration_ids = {event["event_id"] for event in calibration}
        holdout_ids = {event["event_id"] for event in holdout}
        self.assertFalse(calibration_ids & holdout_ids)
        self.assertLess(calibration[-1]["event_date"], holdout[0]["event_date"])
        self.assertGreaterEqual(len(holdout), 2)

    def test_rectification_has_twelve_stable_candidates(self) -> None:
        self.assertEqual(12, len(BRANCH_ORDER))
        self.assertEqual(
            assignment_hash("R1", "E1", "holdout"),
            assignment_hash("R1", "E1", "holdout"),
        )
        self.assertTrue(branches_are_adjacent("子", "亥"))
        self.assertTrue(branches_are_adjacent("子", "丑"))
        self.assertFalse(branches_are_adjacent("子", "卯"))

    def test_chart_without_time_never_invents_hour_pillar(self) -> None:
        chart = calculate_chart("2018-04-05", None, "unknown")
        self.assertIsNotNone(chart)
        assert chart is not None
        self.assertEqual("戊戌", chart["year_pillar"])
        self.assertEqual("丁卯", chart["day_pillar"])
        self.assertIsNone(chart["hour_pillar"])
        self.assertEqual(3, len(chart["ten_god_tags"]))

    def test_chart_with_time_has_hour_detail(self) -> None:
        chart = calculate_chart("2018-04-05", "05:25", "exact")
        self.assertIsNotNone(chart)
        assert chart is not None
        self.assertIsNotNone(chart["hour_pillar"])
        self.assertEqual(4, len(chart["ten_god_tags"]))
        self.assertIn("ming_gong", chart["details"])

    def test_xian_true_solar_time_crosses_hour_boundary(self) -> None:
        solar_clock, correction = true_solar_time(datetime(2018, 4, 5, 5, 25), 108.94, "Asia/Shanghai")
        self.assertLess(correction, -40)
        self.assertEqual(4, solar_clock.hour)

    def test_relation_tags_detect_clash(self) -> None:
        self.assertIn("地支六冲:子午", relation_tags(["甲", "乙"], ["子", "午"]))

    def test_gate_degrades_unsupported_module(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            CREATE TABLE assessment (
              quality_level TEXT, birth_score INTEGER, event_score INTEGER,
              source_score INTEGER, overall_score INTEGER, max_report_level TEXT,
              allowed_modules_json TEXT, blocked_modules_json TEXT, reason_codes_json TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO assessment VALUES ('L2', 65, 0, 80, 47, 'three_pillar_contextual', ?, ?, ?)",
            ('["three_pillars"]', '["precise_timing"]', '["TIME_UNKNOWN_OR_UNRELIABLE"]'),
        )
        row = conn.execute("SELECT * FROM assessment").fetchone()
        decision = gate_decision(row, ["three_pillars", "precise_timing"])
        self.assertEqual("degrade", decision["decision"])
        self.assertEqual(["precise_timing"], decision["blocked_requested_modules"])


if __name__ == "__main__":
    unittest.main()
