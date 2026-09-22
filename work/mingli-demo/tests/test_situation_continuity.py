from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from narrative_expression import express
from story_narrative import load_topic, load_variants, render_story
from test_story_overlap import context


class SituationContinuityTests(unittest.TestCase):
    def test_private_support_feedback_and_self_presentation_are_separate(self):
        topic = load_topic("structure")
        groups = {row: group["id"] for group in topic["questionGroups"]
                  for rows in group["angles"].values() for row in rows}
        self.assertNotEqual(groups[90], groups[138])
        self.assertNotEqual(groups[72], groups[92])
        self.assertNotEqual(groups[84], groups[150])
        self.assertEqual(groups[90], groups[160])
        self.assertEqual(groups[72], groups[163])
        self.assertEqual(groups[92], groups[166])
        self.assertEqual(groups[84], groups[169])
        self.assertEqual(sorted(groups), list(range(180)))

    def test_new_arcs_preserve_consent_evidence_and_no_guarantees(self):
        topic, bank = load_topic("structure"), load_variants("structure")
        required = {160: "同意", 161: "同意", 162: "协商", 163: "低风险",
                    164: "具体", 165: "影响", 166: "真实", 167: "许可",
                    168: "保证", 169: "条件", 170: "低风险", 171: "责任"}
        self.assertEqual(len(topic["scene"]), 180)
        for row, term in required.items():
            choices = [topic["choice"][row], *bank["rows"][row]["choice"]]
            self.assertGreaterEqual(len(choices), 3)
            self.assertTrue(all(term in choice for choice in choices), (row, choices))

    def test_every_new_option_is_reachable_without_cross_role_mixing(self):
        topic, bank = load_topic("structure"), load_variants("structure")
        self.assertEqual(len(bank["rows"]), 180)
        roles = ("scene", "tension", "choice", "reflection")
        for row in range(160, 172):
            focused = deepcopy(topic)
            focused["entryRows"] = [row]
            options_seen = {role: set() for role in roles}
            with patch("story_narrative.load_topic", return_value=focused):
                for index in range(96):
                    seed = f"situation-continuity-{row}-{index}"
                    result = render_story(seed, context("structure"))
                    self.assertEqual(result, render_story(seed, context("structure")))
                    ev = result["narrativeEvidence"]
                    self.assertEqual(ev["fragmentIds"][:4], [f"structure:{role}:{row}" for role in roles])
                    self.assertNotEqual(*ev["selectionBasis"]["questionLink"]["angles"])
                    self.assertEqual(ev["evidenceType"], "editorial_hypothesis")
                    values = [*result["scenes"][:2], result["items"][0], result["summary"]]
                    for role, actual in zip(roles, values):
                        fragment = f"structure:{role}:{row}"
                        option = ev["paragraphVariants"][fragment]
                        options_seen[role].add(option)
                        choices = [topic[role][row], *bank["rows"][row][role]]
                        self.assertEqual(actual, express(choices[option], seed, fragment))
            for role, options in options_seen.items():
                self.assertEqual(options, set(range(1 + len(bank["rows"][row][role]))))


if __name__ == "__main__":
    unittest.main()
