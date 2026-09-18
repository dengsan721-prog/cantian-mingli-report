from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


DEMO_ROOT = Path(__file__).resolve().parents[1]
if str(DEMO_ROOT) not in sys.path:
    sys.path.insert(0, str(DEMO_ROOT))

from report_engine import generate_report  # noqa: E402
from server import delete_report, get_report, list_reports, save_report  # noqa: E402


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
        self.assertEqual(len(generated["chart"]["pillars"]), 4)
        self.assertTrue(generated["chart"]["trueSolarVariant"]["changesHourPillar"])
        self.assertIn("FEWER_THAN_FIVE_EVENTS", generated["quality"]["reasonCodes"])
        self.assertEqual(len(generated["report"]["sections"]), 10)
        self.assertTrue(all(section.get("scenes") for section in generated["report"]["sections"]))
        self.assertTrue(all(section.get("note") for section in generated["report"]["sections"]))
        self.assertTrue(all(section.get("technical") for section in generated["report"]["sections"]))
        self.assertTrue(all(section.get("insight") for section in generated["report"]["sections"]))
        self.assertEqual(len(generated["report"]["highlights"]), 4)
        self.assertGreater(generated["report"]["foundation"]["stats"]["chartSnapshots"], 1000)

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
        self.assertTrue(all(item["probability"] == 0.083333 for item in generated["rectification"]["candidates"]))
        self.assertIsNone(generated["chart"]["hour_pillar"])

    def test_records_can_be_saved_searched_loaded_and_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            db_path = Path(temporary_directory) / "records.db"
            saved = save_report(db_path, generate_report(exact_payload()))

            matches = list_reports(db_path, "邓易安")
            loaded = get_report(db_path, saved["recordId"])

            self.assertEqual(len(matches), 1)
            self.assertEqual(loaded["input"]["name"], "邓易安")
            self.assertTrue(delete_report(db_path, saved["recordId"]))
            self.assertEqual(list_reports(db_path), [])


if __name__ == "__main__":
    unittest.main()
