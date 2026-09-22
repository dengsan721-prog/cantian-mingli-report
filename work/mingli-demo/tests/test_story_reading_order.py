from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from evaluate_wisdom import report_html
from narrative_engine import narrative_text
from story_narrative import load_topic, render_story
from test_story_overlap import context


ORDER = {
    "support-with-consent-and-followup": ["ask-what-support-means", "revisit-and-adjust"],
    "feedback-that-changes-a-step": ["understand-the-feedback", "try-or-repair"],
    "present-experience-without-misleading": ["show-real-contributions", "adapt-and-clarify"],
    "comparison-that-leads-to-learning": ["name-the-need-and-cost", "learn-in-own-conditions"],
}


class StoryReadingOrderTests(unittest.TestCase):
    def test_reviewed_questions_have_explicit_complete_stage_orders(self):
        groups = {g["id"]: g for g in load_topic("structure")["questionGroups"]}
        for name, order in ORDER.items():
            self.assertEqual(groups[name].get("angleOrder"), order)
            self.assertEqual(set(order), set(groups[name]["angles"]))
        group = groups["present-experience-without-misleading"]
        self.assertEqual(group["angles"]["show-real-contributions"], [92, 150, 166, 172, 173])
        self.assertEqual(group["angles"]["adapt-and-clarify"], [167, 168, 174])

    def test_order_only_changes_presentation_not_selected_text_or_canonical_metric(self):
        topic = load_topic("structure")
        seen = set()
        for group in topic["questionGroups"]:
            if group["id"] not in ORDER:
                continue
            for row in [i for rows in group["angles"].values() for i in rows]:
                focused = deepcopy(topic)
                focused["entryRows"] = [row]
                unordered = deepcopy(focused)
                for item in unordered["questionGroups"]:
                    item.pop("angleOrder", None)
                for offset in range(12):
                    seed = f"stage-order-{row}-{offset}"
                    with patch("story_narrative.load_topic", return_value=unordered):
                        old = render_story(seed, context("structure"))
                    with patch("story_narrative.load_topic", return_value=focused):
                        actual = render_story(seed, context("structure"))
                        self.assertEqual(actual, render_story(seed, context("structure")))
                    order = actual.get("narrativeArcOrder")
                    self.assertIsNotNone(order)
                    self.assertEqual(sorted(order), [0, 1])
                    seen.add(tuple(order))
                    before, after = old["narrativeEvidence"], actual["narrativeEvidence"]
                    for key in ("fragmentIds", "paragraphVariants", "selectionBasis"):
                        self.assertEqual(before[key], after[key])
                    for key in ("summary", "scenes", "items", "insight"):
                        self.assertEqual(old[key], actual[key])
                    self.assertEqual(narrative_text({"sections": [old]}), narrative_text({"sections": [actual]}))
                    angles = after["selectionBasis"]["questionLink"]["angles"]
                    self.assertEqual([angles[i] for i in order], ORDER[group["id"]])
                    selected = {int(value.rsplit(":", 1)[1]) for value in after["fragmentIds"]}
                    self.assertFalse(166 in selected and bool(selected & {92, 150}))
        self.assertEqual(seen, {(0, 1), (1, 0)})

    def test_unreviewed_questions_keep_existing_order(self):
        topic = deepcopy(load_topic("structure"))
        topic["entryRows"] = [0]
        with patch("story_narrative.load_topic", return_value=topic):
            result = render_story("unreviewed-order", context("structure"))
        self.assertEqual(result.get("narrativeArcOrder"), [0, 1])
        self.assertFalse(result["narrativeEvidence"]["readingOrder"]["applied"])

    def test_export_moves_whole_arcs_and_keeps_user_observation_after_examples(self):
        section = {"title": "主题", "summary": "洞见甲", "insight": "洞见乙",
                   "scenes": ["场景甲", "解释甲", "场景乙", "解释乙", "用户事实<原文>"],
                   "items": ["行动甲", "行动乙"], "note": "情境不是实际经历",
                   "narrativeLayout": "paired_arcs", "narrativeArcOrder": [1, 0]}
        person = {"name": "测试", "birthDate": "1990-01-01", "birthplace": "未知", "source": "https://example.org"}
        output = report_html(person, {"sections": [section]}, "test")
        ordered = ["场景乙", "解释乙", "洞见乙", "行动乙", "场景甲", "解释甲", "洞见甲", "行动甲", "用户事实&lt;原文&gt;"]
        self.assertEqual([output.index(text) for text in ordered], sorted(output.index(text) for text in ordered))
        self.assertEqual(output.count("情境一"), 1)
        self.assertEqual(output.count("情境二"), 1)
        for text in ordered:
            self.assertEqual(output.count(text), 1)


if __name__ == "__main__":
    unittest.main()
