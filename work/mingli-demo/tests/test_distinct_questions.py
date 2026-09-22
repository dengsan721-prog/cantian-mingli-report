from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from narrative_expression import express
from story_narrative import load_applicability, load_topic, load_variants, render_story
from test_story_overlap import context


class DistinctQuestionsTests(unittest.TestCase):
    def test_new_topics_retain_distinct_practical_questions(self):
        expected = {172: ("失败", "show-real-contributions"), 173: ("分工", "show-real-contributions"),
                    174: ("试做", "adapt-and-clarify"), 175: ("新增", "try-or-repair"),
                    176: ("反馈", "understand-the-feedback"), 177: ("导出", "before-adoption"),
                    178: ("入口", "before-adoption"), 179: ("用途", "reconsider-the-routine")}
        topic = load_topic("structure")
        angles = {row: angle for group in topic["questionGroups"] for angle, rows in group["angles"].items() for row in rows}
        for row, (term, angle) in expected.items():
            self.assertIn(term, topic["choice"][row])
            self.assertEqual(angles[row], angle)
        review = load_topic("review")
        for row, term in {178: "缺失", 179: "休息", 180: "密码", 181: "无效尝试"}.items():
            self.assertIn(term, review["choice"][row])
        self.assertEqual(len(topic["scene"]), 180)
        self.assertEqual(len(review["scene"]), 182)

    def test_all_new_paragraph_choices_are_reachable_and_keep_their_roles(self):
        for name, start, stop, minimum_count in (("structure", 172, 180, 3), ("review", 178, 182, 2)):
            topic, bank = load_topic(name), load_variants(name)
            for row in range(start, stop):
                focused = deepcopy(topic)
                focused["entryRows"] = [row]
                seen = {role: set() for role in ("scene", "tension", "choice", "reflection")}
                with patch("story_narrative.load_topic", return_value=focused):
                    for index in range(96):
                        seed = f"distinct-question-{name}-{row}-{index}"
                        result = render_story(seed, context(name))
                        self.assertEqual(result, render_story(seed, context(name)))
                        evidence = result["narrativeEvidence"]
                        self.assertEqual(evidence["fragmentIds"][0], f"{name}:scene:{row}")
                        self.assertNotEqual(*evidence["selectionBasis"]["questionLink"]["angles"])
                        self.assertEqual(evidence["evidenceType"], "editorial_hypothesis")
                        values = [*result["scenes"][:2], result["items"][0], result["summary"]]
                        for role, text in zip(seen, values):
                            fragment = f"{name}:{role}:{row}"
                            option = evidence["paragraphVariants"][fragment]
                            seen[role].add(option)
                            choices = [topic[role][row], *bank["rows"][row][role]]
                            self.assertGreaterEqual(len(choices), minimum_count)
                            self.assertEqual(text, express(choices[option], seed, fragment))
                for role, options in seen.items():
                    self.assertEqual(options, set(range(1 + len(bank["rows"][row][role]))))

    def test_known_cross_chapter_repeats_have_shared_groups(self):
        groups = load_applicability()["overlapGroups"]
        self.assertEqual(groups.get("bounded-work-trial"), ["structure:174", "career:78"])
        self.assertEqual(groups.get("correction-versus-new-scope"), ["structure:175", "review:93"])
        self.assertEqual(groups.get("share-maintenance-dependencies"), ["structure:48", "career:9", "review:179", "review:180"])
        self.assertEqual(groups.get("credit-real-contributions"), ["structure:173", "career:110"])


if __name__ == "__main__":
    unittest.main()
