from __future__ import annotations

import sys
import tempfile
import unittest
from difflib import SequenceMatcher
from itertools import combinations
from pathlib import Path


DEMO_ROOT = Path(__file__).resolve().parents[1]
if str(DEMO_ROOT) not in sys.path:
    sys.path.insert(0, str(DEMO_ROOT))

from report_engine import WISDOM_MODEL_VERSION, generate_report, lunar_year_options, resolve_birthplace  # noqa: E402
from narrative_engine import narrative_similarity, narrative_text  # noqa: E402
from server import DemoHandler, delete_report, get_report, list_reports, save_report  # noqa: E402


def exact_payload() -> dict[str, object]:
    return {
        "name": "邓易安",
        "gender": "male",
        "calendarType": "solar",
        "year": 2018,
        "month": 4,
        "day": 5,
        "timeText": "05:25",
        "birthplace": "陕西省西安市雁塔区",
        "longitude": 108.94,
        "latitude": 34.34,
        "timezone": "Asia/Shanghai",
        "calendarVerified": True,
        "timeStandardVerified": True,
        "events": [],
    }


class ReportEngineTests(unittest.TestCase):
    def test_wisdom_report_is_the_formal_server_default(self) -> None:
        self.assertEqual(WISDOM_MODEL_VERSION, "wisdom-report-v86")
        self.assertTrue(DemoHandler.use_wisdom)

    def test_lunar_date_is_converted_before_chart_calculation(self) -> None:
        payload = exact_payload()
        payload.update({
            "name": "邓鑫",
            "calendarType": "lunar",
            "year": 1989,
            "month": 3,
            "day": 1,
            "timeText": "亥时",
        })

        generated = generate_report(payload)

        self.assertEqual(generated["input"]["solarDate"], "1989-04-06")
        self.assertEqual(generated["chart"]["pillars"], ["己巳", "戊辰", "丙申", "己亥"])

    def test_exact_time_includes_true_solar_variant_and_quality_limits(self) -> None:
        generated = generate_report(exact_payload())

        self.assertEqual(generated["quality"]["level"], "L3")
        self.assertEqual(generated["quality"]["maxReportLevel"], "四柱综合报告")
        self.assertEqual(len(generated["chart"]["pillars"]), 4)
        self.assertTrue(generated["chart"]["trueSolarVariant"]["changesHourPillar"])
        self.assertIsNotNone(generated["chart"]["trueSolarVariant"]["alternateChart"])
        self.assertIn("FEWER_THAN_FIVE_EVENTS", generated["quality"]["reasonCodes"])
        self.assertEqual(len(generated["report"]["sections"]), 10)
        self.assertTrue(all(section.get("scenes") for section in generated["report"]["sections"]))
        self.assertTrue(all(section.get("note") for section in generated["report"]["sections"]))
        self.assertTrue(all(section.get("technical") for section in generated["report"]["sections"]))
        self.assertTrue(all(section.get("insight") for section in generated["report"]["sections"]))
        self.assertEqual(len(generated["report"]["highlights"]), 4)
        self.assertGreaterEqual(len(generated["report"]["claims"]), 5)
        self.assertTrue(all(item["evidence"] for item in generated["report"]["claims"]))
        self.assertTrue(generated["chart"]["luckCycles"]["cycles"])
        foundation = generated["report"]["foundation"]
        self.assertGreater(foundation["stats"]["chartSnapshots"], 1000)
        self.assertGreater(foundation["coverage"]["birthSpanYears"], 1000)
        self.assertGreater(foundation["validation"]["rectificationRuns"], 100)
        self.assertGreaterEqual(len(foundation["representativePeople"]), 4)
        self.assertEqual(len(foundation["similarFigures"]), 3)
        self.assertTrue(all(0 <= item["distance"] <= 100 for item in foundation["similarFigures"]))
        self.assertEqual(len(foundation["correctionPaths"]), 2)

    def test_unknown_time_never_selects_a_branch(self) -> None:
        payload = exact_payload()
        payload["timeText"] = "不详"
        payload["events"] = [
            {"date": "2008-09", "type": "教育", "summary": "进入大学"},
            {"date": "2012-07", "type": "事业", "summary": "开始工作"},
            {"date": "2015-05", "type": "迁移", "summary": "迁居外地"},
            {"date": "2018-10", "type": "关系", "summary": "登记结婚"},
            {"date": "2022-03", "type": "事业", "summary": "岗位变化"},
        ]

        generated = generate_report(payload)

        self.assertEqual(generated["rectification"]["status"], "candidate_only")
        self.assertEqual(len(generated["rectification"]["candidates"]), 12)
        self.assertEqual(generated["rectification"]["rankingMethod"], "experimental_structural_match_v1")
        self.assertTrue(all("matchScore" in item for item in generated["rectification"]["candidates"]))
        self.assertGreater(
            len({item["matchScore"] for item in generated["rectification"]["candidates"]}),
            1,
        )
        self.assertEqual(generated["rectification"]["calibrationEventCount"], 3)
        self.assertEqual(generated["rectification"]["holdoutEventCount"], 2)
        self.assertIsNone(generated["chart"]["hour_pillar"])

    def test_lunar_options_and_place_resolution_are_calendar_aware(self) -> None:
        options = lunar_year_options(2020)
        self.assertEqual(options["leapMonth"], 4)
        leap_month = next(item for item in options["months"] if item["isLeap"])
        self.assertEqual(leap_month["month"], 4)
        place = resolve_birthplace("陕西省宝鸡市陈仓区周原镇马家沟村")
        self.assertEqual(place["label"], "陕西省宝鸡市陈仓区")
        self.assertEqual(place["timezone"], "Asia/Shanghai")

    def test_gender_changes_luck_cycle_direction_without_changing_base_chart(self) -> None:
        male = generate_report(exact_payload())
        payload = exact_payload()
        payload["gender"] = "female"
        female = generate_report(payload)
        self.assertEqual(male["chart"]["pillars"], female["chart"]["pillars"])
        self.assertNotEqual(
            male["chart"]["luckCycles"]["direction"],
            female["chart"]["luckCycles"]["direction"],
        )

    def test_birthplace_can_fill_coordinates_and_timezone(self) -> None:
        payload = exact_payload()
        payload["longitude"] = None
        payload["latitude"] = None
        payload["timezone"] = None
        generated = generate_report(payload)
        self.assertEqual(generated["input"]["geoSource"], "内置行政区坐标库")
        self.assertIsNotNone(generated["chart"]["trueSolarVariant"])

    def test_records_can_be_saved_searched_loaded_and_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            db_path = Path(temporary_directory) / "records.db"
            saved = save_report(db_path, generate_report(exact_payload()))
            reused = save_report(db_path, generate_report(exact_payload()))
            alias_payload = exact_payload()
            alias_payload["birthplace"] = "西北妇幼保健院"
            reused_alias = save_report(db_path, generate_report(alias_payload))

            matches = list_reports(db_path, "邓易安")
            loaded = get_report(db_path, saved["recordId"])

            self.assertEqual(len(matches), 1)
            self.assertTrue(reused["reused"])
            self.assertTrue(reused_alias["reused"])
            self.assertEqual(saved["recordId"], reused["recordId"])
            self.assertEqual(saved["recordId"], reused_alias["recordId"])
            self.assertEqual(loaded["input"]["name"], "邓易安")
            self.assertTrue(delete_report(db_path, saved["recordId"]))
            self.assertEqual(list_reports(db_path), [])

    def test_cross_person_narratives_stay_below_thirty_percent_similarity(self) -> None:
        fixtures = [
            {"name": "甲", "gender": "male", "year": 1989, "month": 4, "day": 6, "timeText": "22:00", "birthplace": "西安"},
            {"name": "乙", "gender": "male", "year": 1991, "month": 5, "day": 22, "timeText": "00:30", "birthplace": "商洛"},
            {"name": "丙", "gender": "male", "year": 2018, "month": 4, "day": 5, "timeText": "05:25", "birthplace": "西安"},
            {"name": "丁", "gender": "female", "year": 1988, "month": 11, "day": 29, "timeText": "12:00", "birthplace": "宝鸡"},
            {"name": "戊", "gender": "female", "year": 1965, "month": 12, "day": 8, "timeText": "unknown", "birthplace": "宝鸡"},
            {"name": "己", "gender": "male", "year": 1961, "month": 9, "day": 27, "timeText": "unknown", "birthplace": "香港"},
        ]
        reports = []
        for fixture in fixtures:
            payload = exact_payload()
            payload.update(fixture)
            reports.append(generate_report(payload)["report"])

        for (left_index, left), (right_index, right) in combinations(enumerate(reports), 2):
            pair = f"fixture {left_index + 1} / fixture {right_index + 1}"
            self.assertLess(narrative_similarity(left, right, width=7), 0.30, pair)
            self.assertLess(
                SequenceMatcher(None, narrative_text(left), narrative_text(right), autojunk=False).ratio(),
                0.30,
                pair,
            )


if __name__ == "__main__":
    unittest.main()
