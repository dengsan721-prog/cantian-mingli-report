from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from story_narrative import load_applicability, load_topic, render_story
from test_story_overlap import context


class StructureCoherenceTests(unittest.TestCase):
    def test_every_scene_has_one_question_and_complementary_angles(self):
        topic = load_topic("structure")
        self.assertEqual(topic.get("questionVersion"), "structure-question-links-v4")
        assigned = {}
        for group in topic["questionGroups"]:
            self.assertTrue(group["title"].startswith("内在动力："))
            self.assertTrue(group["question"].endswith("？"))
            self.assertGreaterEqual(len(group["angles"]), 2)
            for angle, indices in group["angles"].items():
                self.assertTrue(indices)
                for row in indices:
                    self.assertNotIn(row, assigned)
                    assigned[row] = (group["id"], angle)
        self.assertEqual(sorted(assigned), list(range(len(topic["scene"]))))
        self.assertEqual(assigned[155][0], assigned[5][0])
        self.assertNotEqual(assigned[155][0], assigned[131][0])
        self.assertNotEqual(assigned[158][0], assigned[6][0])
        self.assertEqual(assigned[113][0], assigned[152][0])

    def test_every_entry_preserves_its_arc_and_stays_in_its_question(self):
        topic = load_topic("structure")
        groups = {g["id"]: g for g in topic.get("questionGroups", [])}
        reached = set()
        for row in range(len(topic["scene"])):
            focused = deepcopy(topic)
            focused["entryRows"] = [row]
            legacy = {k: v for k, v in focused.items() if not k.startswith("question")}
            for axis in (*load_applicability()["axes"], "综合承接"):
                seed = f"structure-common-question-{row}"
                ctx = context("structure", axis)
                with patch("story_narrative.load_topic", return_value=legacy):
                    old = render_story(seed, ctx)
                with patch("story_narrative.load_topic", return_value=focused):
                    result = render_story(seed, ctx)
                    self.assertEqual(result, render_story(seed, ctx))
                evidence = result["narrativeEvidence"]
                basis = evidence["selectionBasis"]
                link = basis["questionLink"]
                self.assertTrue(link["applied"])
                group = groups[link["id"]]
                self.assertEqual(evidence["fragmentIds"][:4], old["narrativeEvidence"]["fragmentIds"][:4])
                self.assertEqual(result["scenes"][:2], old["scenes"][:2])
                self.assertEqual(result["summary"], old["summary"])
                self.assertEqual(result["items"][0], old["items"][0])
                self.assertEqual(result["title"], group["title"])
                self.assertNotEqual(*link["angles"])
                for offset, angle in zip((0, 4), link["angles"]):
                    chosen = int(evidence["fragmentIds"][offset].rsplit(":", 1)[1])
                    self.assertIn(chosen, group["angles"][angle])
                self.assertEqual(basis["counterAxisApplied"],
                                 basis["counterTag"] is not None and basis["counterTag"] in basis["selectedTags"][1])
                self.assertEqual(evidence["evidenceType"], "editorial_hypothesis")
                reached.add(link["id"])
        self.assertEqual(reached, set(groups))

    def test_overlap_exhaustion_does_not_escape_common_question(self):
        catalog = deepcopy(load_applicability())
        catalog["overlapGroups"] = {"all-structure": [f"structure:{i}" for i in range(180)]}
        with patch("story_narrative.load_applicability", return_value=catalog):
            result = render_story("structure-exhaustion", context("structure"), {"all-structure"})
        basis = result["narrativeEvidence"]["selectionBasis"]
        self.assertTrue(basis["questionLink"]["applied"])
        self.assertNotEqual(*basis["questionLink"]["angles"])
        self.assertEqual(basis["reportContrast"]["reusedGroups"], ["all-structure"])


if __name__ == "__main__":
    unittest.main()
