import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from freeze_public_holdout import build_plan


def person(identifier, day):
    return {'public_person_id': identifier, 'primary_name': identifier, 'gender': 'male',
            'date_standard': f'1980-01-{day:02d}', 'place_raw': ''}


class HoldoutPlanTests(unittest.TestCase):
    def test_excludes_known_ids_and_equivalent_inputs_without_scoring(self):
        used = person('WD_1', 1)
        pool = {'seed': 1, 'eligibleSha256': 'pool', 'eligibleCount': 5,
                'selected': [person('WD_1', 2), person('WD_alias', 1),
                             person('WD_4', 4), person('WD_3', 3), person('WD_5', 5)]}
        prior = {'development/cohort.json': {'selected': [used]}}
        first = build_plan(pool, prior, 2)
        self.assertEqual(first, build_plan(pool, prior, 2))
        self.assertEqual([p['public_person_id'] for p in first['candidateOrder']], ['WD_4', 'WD_3', 'WD_5'])
        self.assertEqual(first['requestedSampleSize'], 2)
        self.assertEqual(first['excludedPublicRecordCount'], 1)
        self.assertEqual(first['excludedInputCount'], 1)
        self.assertEqual(first['remainingCandidateCount'], 3)
        self.assertNotIn('metrics', first)

    def test_short_pool_is_not_filled_with_excluded_records(self):
        p = person('WD_1', 1)
        pool = {'seed': 1, 'eligibleSha256': 'pool', 'eligibleCount': 1, 'selected': [p]}
        with self.assertRaises(ValueError):
            build_plan(pool, {'dev': {'selected': [p]}}, 2)

    def test_unknown_exclusion_schema_does_not_silently_pass(self):
        pool = {'seed': 1, 'eligibleSha256': 'pool', 'eligibleCount': 2,
                'selected': [person('WD_1', 1), person('WD_2', 2)]}
        with self.assertRaises(KeyError):
            build_plan(pool, {'unrecognized': {'people': []}}, 2)
