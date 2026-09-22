from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from story_narrative import load_applicability, load_topic, load_variants, render_story
from test_story_overlap import context


class ConversationDepthTests(unittest.TestCase):
    def test_reclaiming_a_turn_is_one_need_not_two_complementary_scenes(self):
        topic = load_topic("relationships")
        group = next(g for g in topic["questionGroups"] if g["id"] == "voice-heard")
        angles = {row: angle for angle, rows in group["angles"].items() for row in rows}
        self.assertEqual(angles[36], angles[51])
        repeated = {36, 51, 76}
        self.assertEqual(load_applicability()["overlapGroups"]["keep-shared-story-in-focus"],
                         [f"relationships:{row}" for row in sorted(repeated)])
        for first in sorted(repeated):
            focused = deepcopy(topic)
            focused["entryRows"] = [first]
            with patch("story_narrative.load_topic", return_value=focused):
                for index in range(96):
                    result = render_story(f"turn-taking-{index}", context("relationships"))
                    proof = result["narrativeEvidence"]
                    chosen = {int(proof["fragmentIds"][offset].rsplit(":", 1)[1]) for offset in (0, 4)}
                    self.assertEqual(len(chosen & repeated), 1)
                    self.assertFalse(proof["selectionBasis"]["reportContrast"]["reusedGroups"])

    def test_fair_access_advice_does_not_recur_in_review(self):
        group = "fair-shared-access"
        self.assertEqual(load_applicability()["overlapGroups"][group], ["portrait:46", "review:120"])
        for axis in (*load_applicability()["axes"], "综合承接"):
            for index in range(96):
                result = render_story(f"shared-access-{index}", context("review", axis), {group})
                self.assertNotIn("review:scene:120", result["narrativeEvidence"]["fragmentIds"])

    def test_new_angles_are_complete_reachable_and_keep_distinct_purposes(self):
        topic, bank = load_topic("relationships"), load_variants("relationships")
        group = next(g for g in topic["questionGroups"] if g["id"] == "voice-heard")
        self.assertIn(140, group["angles"]["speak"])
        self.assertEqual(group["angles"]["understand-without-endorsing"], [141])
        self.assertEqual(group["angles"]["answer-after-listening"], [142])
        constraints = {
            140: ("不把猜测说成事实", "不替对方断定动机", "不以一次经过概括整个人"),
            141: ("不附和未经核实的指控", "不将认同感受变成指控他人的证据", "不为未知事实作保证"),
            142: ("不把收集意见说成已经获得同意", "不把未反对当作授权", "不能替受影响者作出承诺"),
        }
        for row, phrases in constraints.items():
            focused = deepcopy(topic)
            focused["entryRows"] = [row]
            choices = [topic["choice"][row], *bank["rows"][row]["choice"]]
            self.assertEqual(len(choices), len(phrases))
            for choice, phrase in zip(choices, phrases):
                self.assertIn(phrase, choice)
            reached = {role: set() for role in ("scene", "tension", "choice", "reflection")}
            with patch("story_narrative.load_topic", return_value=focused):
                for index in range(96):
                    seed = f"new-conversation-{row}-{index}"
                    result = render_story(seed, context("relationships"))
                    self.assertEqual(result, render_story(seed, context("relationships")))
                    proof = result["narrativeEvidence"]
                    self.assertEqual(proof["fragmentIds"][0], f"relationships:scene:{row}")
                    self.assertEqual(proof["evidenceType"], "editorial_hypothesis")
                    self.assertNotEqual(*proof["selectionBasis"]["questionLink"]["angles"])
                    for role in reached:
                        reached[role].add(proof["paragraphVariants"][f"relationships:{role}:{row}"])
            self.assertTrue(all(options == {0, 1, 2} for options in reached.values()))


if __name__ == "__main__":
    unittest.main()
