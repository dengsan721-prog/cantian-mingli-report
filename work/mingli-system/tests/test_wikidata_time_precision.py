import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from import_wikidata_entities import claim_time, date_precision, normalize_wikidata_time, qualifier_time


class WikidataTimePrecisionTests(unittest.TestCase):
    def test_placeholders_do_not_upgrade_precision(self):
        raw = '+2001-01-01T00:00:00Z'
        self.assertEqual(normalize_wikidata_time(raw, 9), '2001-00-00')
        self.assertEqual(date_precision(normalize_wikidata_time(raw, 9)), 'year')
        self.assertEqual(normalize_wikidata_time(raw, 10), '2001-01-00')
        self.assertEqual(date_precision(normalize_wikidata_time(raw, 10)), 'month')
        self.assertEqual(normalize_wikidata_time(raw, 11), '2001-01-01')
        self.assertIsNone(normalize_wikidata_time(raw, 8))
        self.assertIsNone(normalize_wikidata_time(raw))
        self.assertEqual(normalize_wikidata_time('-0044-03-15T00:00:00Z', 9), '-0044-00-00')

    def test_birth_claims_and_event_qualifiers_preserve_source_precision(self):
        value = {'time': '+2001-01-01T00:00:00Z', 'precision': 9}
        entity = {'claims': {'P569': [{'mainsnak': {'datavalue': {'value': value}}}]}}
        self.assertEqual(claim_time(entity, 'P569'), '2001-00-00')
        statement = {'qualifiers': {'P585': [{'datavalue': {'value': value}}]}}
        self.assertEqual(qualifier_time(statement, 'P585'), '2001-00-00')


if __name__ == '__main__':
    unittest.main()
