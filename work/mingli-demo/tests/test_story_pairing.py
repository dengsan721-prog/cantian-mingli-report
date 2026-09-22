from copy import deepcopy
import hashlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from story_narrative import load_applicability, load_topic, render_story
from test_story_overlap import context


def fixture():
    topic = deepcopy(load_topic("structure"))
    topic["entryRows"] = [0]
    topic["questionGroups"] = [{"id": "one-question", "title": "Editorial test",
                                "question": "One shared question?",
                                "angles": {"observation": [0], "response": [1, 2, 3]}}]
    catalog = deepcopy(load_applicability())
    catalog["topics"]["structure"] = [["A"], ["O"], ["L"], ["E"]] + [["A"]] * 156
    catalog["overlapGroups"] = {}
    return topic, catalog


class StoryPairingTests(unittest.TestCase):
    def test_question_angles_are_not_collapsed_to_one_counter_axis_row(self):
        topic, catalog = fixture()
        selected = set()
        with patch("story_narrative.load_topic", return_value=topic), \
                patch("story_narrative.load_applicability", return_value=catalog):
            for index in range(128):
                seed = f"angle-pool-{index}"
                result = render_story(seed, context("structure", "自主驱动"))
                proof = result["narrativeEvidence"]
                basis = proof["selectionBasis"]
                self.assertEqual(basis["counterpartCount"], 3)
                self.assertEqual(basis["counterpartPolicy"], "same_question_other_angle")
                self.assertEqual(proof["fragmentIds"][0], "structure:scene:0")
                row = int(proof["fragmentIds"][4].rsplit(":", 1)[1])
                expected = min((1, 2, 3), key=lambda i: hashlib.sha256(
                    f"{seed}|structure|counter|{i}".encode()).digest())
                self.assertEqual(row, expected)
                self.assertEqual(basis["counterAxisApplied"], row == 1)
                self.assertEqual(basis["questionLink"]["angles"], ["observation", "response"])
                self.assertEqual(result, render_story(seed, context("structure", "自主驱动")))
                selected.add(row)
        self.assertEqual(selected, {1, 2, 3})

    def test_prior_overlap_exclusions_still_precede_pair_selection(self):
        topic, catalog = fixture()
        catalog["overlapGroups"] = {"already-covered": ["structure:1", "structure:2"]}
        with patch("story_narrative.load_topic", return_value=topic), \
                patch("story_narrative.load_applicability", return_value=catalog):
            result = render_story("exclude-near-duplicates", context("structure", "自主驱动"), {"already-covered"})
        proof = result["narrativeEvidence"]
        self.assertEqual(proof["fragmentIds"][4], "structure:scene:3")
        self.assertEqual(proof["selectionBasis"]["counterpartCount"], 1)
        self.assertFalse(proof["selectionBasis"]["counterAxisApplied"])
        self.assertFalse(proof["selectionBasis"]["reportContrast"]["reusedGroups"])

    def test_secondary_scope_and_scene_family_limits_are_retained(self):
        topic, catalog = fixture()
        topic["secondaryRows"] = [1, 2]
        topic["families"] = ["same", "same", "different", "different"] + ["unused"] * 156
        with patch("story_narrative.load_topic", return_value=topic), \
                patch("story_narrative.load_applicability", return_value=catalog):
            result = render_story("scoped-alternatives", context("structure", "自主驱动"))
        proof = result["narrativeEvidence"]
        self.assertEqual(proof["fragmentIds"][4], "structure:scene:2")
        self.assertTrue(proof["selectionBasis"]["secondaryRestricted"])
        self.assertTrue(proof["selectionBasis"]["familyContrast"]["applied"])

    def test_unlinked_topics_keep_the_existing_counter_axis_policy(self):
        topic, catalog = fixture()
        topic = {k: v for k, v in topic.items() if not k.startswith("question")}
        with patch("story_narrative.load_topic", return_value=topic), \
                patch("story_narrative.load_applicability", return_value=catalog):
            for index in range(32):
                result = render_story(f"unlinked-{index}", context("structure", "自主驱动"))
                proof = result["narrativeEvidence"]
                self.assertEqual(proof["fragmentIds"][4], "structure:scene:1")
                self.assertEqual(proof["selectionBasis"]["counterpartPolicy"], "traditional_counter_axis_fallback")
                self.assertFalse(proof["selectionBasis"]["questionLink"]["applied"])


if __name__ == "__main__":
    unittest.main()
