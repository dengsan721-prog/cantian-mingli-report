from copy import deepcopy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from narrative_diversity import body_text
from narrative_engine import narrative_text
from report_engine import generate_report
from test_report_engine import exact_payload
from wisdom_narrative import render_followthrough


class FollowthroughTests(unittest.TestCase):
    def test_adult_closing_reuses_explained_choices_with_traceable_sources(self):
        for year in (1940, 1960, 1980, 1991, 2000):
            report = generate_report({**exact_payload(), "year": year}, use_wisdom=True)["report"]
            sections = report["sections"]
            by_id = {section["id"]: section for section in sections}
            self.assertEqual(len(by_id), 10)
            self.assertEqual([s["id"] for s in sections[:3]], ["portrait", "structure", "character"])
            self.assertEqual([s["id"] for s in sections[-2:]], ["review", "actions"])
            closing = sections[-1]
            links = closing["narrativeEvidence"]["linkedActions"]
            self.assertEqual(len(links), 3)
            self.assertEqual(len({link["sectionId"] for link in links}), 3)
            self.assertEqual(closing["scenes"], [])
            for item, link in zip(closing["items"], links):
                source = by_id[link["sectionId"]]
                self.assertNotEqual(source["id"], "actions")
                self.assertEqual(item, source["items"][link["itemIndex"]])
                self.assertIn(link["fragmentId"], source["narrativeEvidence"]["fragmentIds"])
            self.assertEqual(closing["summary"], "")
            self.assertEqual(closing["insight"], "")
            self.assertNotIn("linkedReflections", closing["narrativeEvidence"])
            self.assertEqual(closing["narrativeEvidence"]["fragmentIds"],
                             [link["fragmentId"] for link in links])
            self.assertIn("汇总前文", closing["technical"])
            self.assertEqual(body_text(sections), narrative_text(report))
            self.assertTrue(all(item in body_text(sections) for item in closing["items"]))

    def test_priority_is_deduplicated_and_recap_does_not_mutate_sources(self):
        report = generate_report({**exact_payload(), "year": 1991}, use_wisdom=True)["report"]
        sources = report["sections"][:-1]
        before = deepcopy(sources)
        result = render_followthrough(sources, ["wealth", "wealth", "relationships"])
        self.assertEqual(sources, before)
        self.assertEqual([link["sectionId"] for link in result["narrativeEvidence"]["linkedActions"]],
                         ["wealth", "relationships", "wellbeing"])
        self.assertEqual(result, render_followthrough(sources, ["wealth", "wealth", "relationships"]))

    def test_youth_closing_stays_in_its_developmental_band(self):
        for year, band in ((2024, "early_childhood"), (2016, "school_age"), (2010, "teen")):
            report = generate_report({**exact_payload(), "year": year}, use_wisdom=True)["report"]
            closing = report["sections"][-1]
            self.assertEqual(closing["id"], "actions")
            self.assertEqual(closing["narrativeLayout"], "paired_arcs")
            self.assertEqual(closing["narrativeEvidence"]["selectionBasis"]["developmentalBand"], band)
            self.assertNotIn("linkedActions", closing["narrativeEvidence"])


if __name__ == "__main__":
    unittest.main()
