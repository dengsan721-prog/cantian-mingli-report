from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from narrative_expression import express
from story_narrative import load_topic, load_variants, render_story
from test_story_overlap import context


class StructureExpressionDepthTests(unittest.TestCase):
    def test_personal_dynamics_have_two_additional_complete_wordings(self):
        topic, bank = load_topic("structure"), load_variants("structure")
        self.assertEqual(bank["version"], "structure-paragraph-variants-v16")
        self.assertEqual(len(bank["rows"]), 180)
        for row in range(64, 96):
            for role in ("scene", "tension", "choice", "reflection"):
                options = bank["rows"][row][role]
                self.assertEqual(len(options), 5 if row == 67 else 3)
                self.assertTrue(all(len(text) > 20 for text in options[-2:]))
                self.assertEqual(len({topic[role][row], *options}), len(options) + 1)

    def test_new_choices_preserve_material_practical_limits(self):
        bank = load_variants("structure")
        constraints = {
            64: ("已有责任", "责任"), 65: ("调整成本", "收尾"),
            66: ("当时的信息与权限", "责任范围"), 67: ("安全", "安全"),
            68: ("关键未知", "责任"), 69: ("原定标准", "交接"),
            70: ("原有成果", "两轮评价"), 71: ("承诺", "已有责任"),
            72: ("无依据的指责", "经过、影响"), 74: ("重大后果", "重要新信息"),
            75: ("退出责任", "约定和交接"), 76: ("原有责任", "已有承诺"),
            78: ("安全", "安全"), 80: ("必须履行的责任", "不承诺"),
            81: ("不把探索中的内容直接当成定稿", "最终核实"),
            82: ("可核对", "不要求过去"), 83: ("真正紧急", "实际紧急程度"),
            85: ("共同同意", "共同责任"), 86: ("可观察", "未经证明"),
            87: ("无法保证", "不作超出能力的保证"), 89: ("没有新增信息", "不用猜测"),
            90: ("同意", "同意"), 91: ("及时通知并协商", "不为追补"),
            92: ("不把共同成果独占", "不夸大"), 93: ("未知", "未知"),
            94: ("不从一次表现推断固定性格", "自己的判断"),
            95: ("责任已有妥善安排", "必要事项"),
        }
        for row, required in constraints.items():
            choices = bank["rows"][row]["choice"]
            self.assertGreaterEqual(len(choices), 3)
            for text, phrase in zip(choices[-2:], required):
                self.assertIn(phrase, text, (row, text))

    def test_every_option_is_reachable_without_changing_the_selected_plot(self):
        topic, bank = load_topic("structure"), load_variants("structure")
        previous = deepcopy(bank)
        for row in range(64, 96):
            for role in ("scene", "tension", "choice", "reflection"):
                previous["rows"][row][role] = previous["rows"][row][role][:-2]
        for row in range(64, 96):
            focused = deepcopy(topic)
            focused["entryRows"] = [row]
            selected = {role: set() for role in ("scene", "tension", "choice", "reflection")}
            with patch("story_narrative.load_topic", return_value=focused):
                for index in range(128):
                    seed = f"structure-depth-{row}-{index}"
                    result = render_story(seed, context("structure"))
                    with patch("story_narrative.load_variants", return_value=previous):
                        old = render_story(seed, context("structure"))
                    proof, prior = result["narrativeEvidence"], old["narrativeEvidence"]
                    self.assertEqual(proof["fragmentIds"], prior["fragmentIds"])
                    self.assertEqual(proof["selectionBasis"], prior["selectionBasis"])
                    self.assertEqual(proof["evidenceType"], "editorial_hypothesis")
                    self.assertEqual(result, render_story(seed, context("structure")))
                    actual = (result["scenes"][0], result["scenes"][1], result["items"][0], result["summary"])
                    for role, text in zip(selected, actual):
                        fragment = f"structure:{role}:{row}"
                        option = proof["paragraphVariants"][fragment]
                        selected[role].add(option)
                        choices = [topic[role][row], *bank["rows"][row][role]]
                        self.assertEqual(text, express(choices[option], seed, fragment))
                        if option <= len(previous["rows"][row][role]):
                            self.assertEqual(option, prior["paragraphVariants"][fragment])
            for role, options in selected.items():
                self.assertEqual(options, set(range(len(bank["rows"][row][role]) + 1)))


if __name__ == "__main__":
    unittest.main()
