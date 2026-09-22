from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_readability import compare
from evaluate_wisdom import report_html


class ReadingLayoutTests(unittest.TestCase):
    def test_closing_export_links_back_to_existing_chapters(self):
        from report_engine import generate_report
        from test_report_engine import exact_payload
        report = generate_report({**exact_payload(), "year": 1991}, use_wisdom=True)["report"]
        person = {"name": "测试", "birthDate": "1991-01-01", "birthplace": "未知", "source": "https://example.org"}
        output = report_html(person, report, "test")
        closing = report["sections"][-1]
        self.assertEqual(output.count("回看前文"), 3)
        self.assertNotIn("<p class='lead'></p>", output)
        self.assertNotIn("<blockquote></blockquote>", output)
        self.assertIn(closing["listTitle"], output)
        for link in closing["narrativeEvidence"]["linkedActions"]:
            source = link["sectionId"]
            self.assertIn(f'href="#report-{source}"', output)
            self.assertIn(f'id="report-{source}"', output)

    def test_export_keeps_each_arc_together_and_observations_separate(self):
        section = {"title": "主题", "summary": "洞见甲", "insight": "洞见乙",
                   "scenes": ["场景甲", "解释甲", "场景乙", "解释乙", "用户事实<原文>"],
                   "items": ["行动甲", "行动乙"], "note": "情境不是实际经历", "narrativeLayout": "paired_arcs"}
        person = {"name": "测试", "birthDate": "1990-01-01", "birthplace": "未知", "source": "https://example.org"}
        html = report_html(person, {"sections": [section]}, "test")
        ordered = ["场景甲", "解释甲", "洞见甲", "行动甲", "场景乙", "解释乙", "洞见乙", "行动乙", "用户事实&lt;原文&gt;"]
        positions = [html.index(text) for text in ordered]
        self.assertEqual(positions, sorted(positions))
        for text in ordered:
            self.assertEqual(html.count(text), 1)

    def test_diagnostics_preserve_uncertainty_and_do_not_claim_fluency(self):
        row = {"id": "a", "report": {"sections": [{"id": "x", "summary": "可能有用，也可能无效。",
                                                    "narrativeEvidence": {"fragmentIds": ["x:0"]}}]}}
        result = compare([row], [row])
        self.assertEqual(result["before"], result["after"])
        self.assertEqual(result["after"]["terms"]["可能"]["meanPerReport"], 2)
        self.assertEqual(result["unchangedOriginalFragmentSelections"], 1)
        self.assertNotIn("passed", result)
        with self.assertRaises(ValueError):
            compare([row], [{**row, "id": "b"}])


if __name__ == "__main__":
    unittest.main()
