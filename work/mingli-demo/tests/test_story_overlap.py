import sys
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from report_engine import generate_report
from story_narrative import COUNTER_AXIS, load_applicability, load_topic, render_story
from test_report_engine import exact_payload


def context(topic, axis="综合承接"):
    return {"id": topic, "title": "测试", "evidence": "文化解释", "counter": "现实核对",
            "core": "观察", "tension": "条件", "axisDrive": axis}


class StoryOverlapTests(unittest.TestCase):
    def test_catalog_members_resolve_to_complete_original_arcs(self):
        catalog = load_applicability()
        self.assertEqual(catalog["overlapVersion"], "editorial-overlap-v10")
        self.assertEqual(len(catalog["overlapGroups"]), 36)
        self.assertEqual(catalog["overlapGroups"]["skill-exchange-scope"], ["career:125", "wealth:124"])
        self.assertEqual(catalog["overlapGroups"]["schedule-transition-buffer"],
                         ["actions:43", "structure:42", "wealth:42", "wealth:84", "wellbeing:38", "review:173"])
        self.assertEqual(catalog["overlapGroups"]["frequent-item-retrieval"],
                         ["actions:32", "portrait:72", "structure:33", "wealth:67", "wealth:76", "wellbeing:70"])
        for members in catalog["overlapGroups"].values():
            self.assertGreaterEqual(len(members), 2)
            self.assertEqual(len(members), len(set(members)))
            for member in members:
                topic, row = member.rsplit(":", 1)
                for role in ("scene", "tension", "choice", "reflection"):
                    self.assertTrue(load_topic(topic)[role][int(row)])

    def test_daily_arrangement_groups_keep_distinct_needs_available(self):
        groups = load_applicability()["overlapGroups"]
        expected = {
            "inventory-before-purchase": ["actions:39", "wealth:34"],
            "practice-before-equipment": ["actions:22", "wealth:37", "wealth:66", "wealth:86"],
            "task-fit-to-available-slots": ["career:104", "structure:107"],
            "verify-departure-requirements": ["actions:66", "structure:117"],
            "check-tool-workflow-benefit": ["structure:25", "wealth:54"],
            "reconcile-original-agreement": ["character:77", "review:76", "relationships:125", "relationships:80"],
            "organize-self-directed-time": ["structure:79", "turning-points:49"],
            "return-borrowed-items": ["wellbeing:96", "actions:65"],
            "hear-less-visible-participants": ["relationships:71", "relationships:114"],
        }
        for group, members in expected.items():
            self.assertEqual(groups[group], members)
        nearby_but_distinct = {"wellbeing:27", "character:58", "career:119", "wealth:107", "structure:39"}
        arrangement_members = set(groups["schedule-transition-buffer"]) | set(groups["verify-departure-requirements"])
        self.assertFalse(arrangement_members & nearby_but_distinct)

    def test_effort_groups_preserve_distinct_questions(self):
        groups = load_applicability()["overlapGroups"]
        expected = {
            "overexertion-load-and-recovery": ["review:88", "review:116", "wellbeing:51"],
            "match-group-activity-to-capacity": ["portrait:84", "review:116", "wellbeing:126"],
            "replace-willpower-with-environment": ["actions:5", "structure:15", "wealth:30"],
        }
        for group, members in expected.items():
            self.assertEqual(groups[group], members)
        members = {member for group in expected for member in groups[group]}
        self.assertFalse(members & {"career:111", "turning-points:51", "wellbeing:111", "actions:74"})
        for axis in (*load_applicability()["axes"], "综合承接"):
            for index in range(100):
                story = render_story(f"effort-contrast-{index}", context("review", axis))
                scenes = {fragment for fragment in story["narrativeEvidence"]["fragmentIds"] if ":scene:" in fragment}
                self.assertFalse({"review:scene:88", "review:scene:116"} <= scenes)
                constrained = render_story(f"effort-contrast-{index}", context("review", axis),
                                           used_groups={"overexertion-load-and-recovery"})
                self.assertFalse({"review:scene:88", "review:scene:116"} &
                                 set(constrained["narrativeEvidence"]["fragmentIds"]))

    def test_review_does_not_repeat_completed_packing_or_handoff_advice(self):
        required = {
            "carry-only-needed-items": ["wealth:73", "wealth:82", "wellbeing:44", "review:84"],
            "handoff-authorized-access": ["career:75", "review:163"],
            "confirm-availability-window": ["wellbeing:65", "review:134", "review:172"],
            "verify-current-instructions": ["career:76", "review:156"],
        }
        catalog = load_applicability()
        for group, members in required.items():
            self.assertEqual(catalog["overlapGroups"].get(group), members)
            for axis in (*catalog["axes"], "综合承接"):
                for index in range(128):
                    story = render_story(f"review-prior-advice-{index}", context("review", axis), {group})
                    chosen = story["narrativeEvidence"]["fragmentIds"]
                    self.assertFalse({member.replace(":", ":scene:") for member in members} & set(chosen))
                    self.assertFalse(story["narrativeEvidence"]["selectionBasis"]["reportContrast"]["reusedGroups"])
        # Nearby needs are not all the same advice: access, preference and aftercare differ.
        self.assertNotIn("portrait:95", catalog["overlapGroups"]["carry-only-needed-items"])
        self.assertNotIn("review:168", catalog["overlapGroups"]["carry-only-needed-items"])
        self.assertNotIn("relationships:130", catalog["overlapGroups"]["handoff-authorized-access"])

    def test_declared_groups_do_not_repeat_across_chapters_or_arcs(self):
        catalog = load_applicability()
        reached = set()
        excluded = 0
        for axis in (*catalog["axes"], "综合承接"):
            for index in range(80):
                used = set()
                for topic in catalog["topics"]:
                    seed = f"report-overlap-{index}"
                    story = render_story(seed, context(topic, axis), used_groups=used)
                    evidence = story["narrativeEvidence"]
                    proof = evidence["selectionBasis"]["reportContrast"]
                    self.assertFalse(proof["reusedGroups"])
                    chosen = proof["selectedGroups"]
                    self.assertFalse(used & set(chosen))
                    self.assertEqual(chosen, sorted(set(chosen)))
                    self.assertEqual(story, render_story(seed, context(topic, axis), used_groups=used))
                    used.update(chosen)
                    reached.update(chosen)
                    excluded += sum(proof["excludedCandidateCounts"])
        self.assertEqual(reached, set(catalog["overlapGroups"]))
        self.assertGreater(excluded, 0)

    def test_no_known_conflict_preserves_fragment_and_paragraph_choices(self):
        for topic in load_applicability()["topics"]:
            before = render_story("unrelated-groups", context(topic))
            after = render_story("unrelated-groups", context(topic), used_groups={"not-in-catalog"})
            self.assertEqual(before, after)

    def test_unlinked_exhaustion_preserves_axis_and_discloses_reuse(self):
        catalog = deepcopy(load_applicability())
        catalog["overlapGroups"] = {"every-arc": [f"relationships:{i}" for i in range(len(load_topic("relationships")["scene"]))]}
        legacy_topic = {key: value for key, value in load_topic("relationships").items()
                        if not key.startswith("question")}
        used = {"every-arc"}
        with patch("story_narrative.load_applicability", return_value=catalog), \
                patch("story_narrative.load_topic", return_value=legacy_topic):
            story = render_story("exhausted", context("relationships", "自主驱动"), used_groups=used)
        basis = story["narrativeEvidence"]["selectionBasis"]
        self.assertIn(catalog["axes"]["自主驱动"], basis["selectedTags"][0])
        self.assertIn(catalog["axes"][COUNTER_AXIS["自主驱动"]], basis["selectedTags"][1])
        self.assertEqual(basis["reportContrast"]["reusedGroups"], ["every-arc"])
        self.assertEqual(basis["reportContrast"]["excludedCandidateCounts"], [0, 0])
        self.assertEqual(used, {"every-arc"})

    def test_linked_exhaustion_discloses_missing_counter_axis_without_leaving_question(self):
        catalog = deepcopy(load_applicability())
        catalog["overlapGroups"] = {"every-arc": [f"relationships:{i}" for i in range(len(load_topic("relationships")["scene"]))]}
        with patch("story_narrative.load_applicability", return_value=catalog):
            story = render_story("exhausted", context("relationships", "自主驱动"), used_groups={"every-arc"})
        basis = story["narrativeEvidence"]["selectionBasis"]
        link = basis["questionLink"]
        self.assertTrue(link["applied"])
        self.assertNotEqual(*link["angles"])
        self.assertIn(catalog["axes"]["自主驱动"], basis["selectedTags"][0])
        self.assertFalse(basis["counterAxisApplied"])
        self.assertNotIn(basis["counterTag"], basis["selectedTags"][1])
        group = next(g for g in load_topic("relationships")["questionGroups"] if g["id"] == link["id"])
        alternatives = [row for angle, rows in group["angles"].items() if angle != link["angles"][0] for row in rows]
        self.assertTrue(all(basis["counterTag"] not in catalog["topics"]["relationships"][row]
                            for row in alternatives))
        self.assertEqual(basis["reportContrast"]["reusedGroups"], ["every-arc"])
        self.assertEqual(basis["reportContrast"]["excludedCandidateCounts"], [0, 0])

    def test_report_pipeline_passes_only_current_report_groups(self):
        import narrative_engine
        original = narrative_engine.render_wisdom_section
        calls = []

        def checked(seed, ctx, used_groups=None):
            calls.append((ctx["id"], set(used_groups or ())))
            return original(seed, ctx, used_groups=used_groups)

        for month in range(1, 13):
            calls.clear()
            payload = {**exact_payload(), "year": 1990, "month": month, "day": 12}
            with patch("narrative_engine.render_wisdom_section", side_effect=checked):
                report = generate_report(payload, use_wisdom=True)["report"]
            used = set()
            for section, (topic, supplied) in zip(report["sections"], calls):
                self.assertEqual(topic, section["id"])
                self.assertEqual(supplied, used)
                proof = section["narrativeEvidence"]["selectionBasis"]["reportContrast"]
                self.assertFalse(proof["reusedGroups"])
                used.update(proof["selectedGroups"])
            self.assertEqual(len(calls), 9)
            self.assertEqual(report["sections"][-1]["narrativeLayout"], "linked_actions")


if __name__ == "__main__":
    unittest.main()
