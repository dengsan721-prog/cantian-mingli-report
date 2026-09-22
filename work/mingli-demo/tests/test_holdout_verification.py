import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from evaluate_scale import digest
from freeze_public_holdout import build_plan, input_identity
from verify_public_holdout import validate_plan, verify_plan


def person(index):
    return {'public_person_id': f'WD_Q{index}', 'primary_name': f'合成核验样本{index}',
            'gender': 'male', 'date_standard': f'{1920 + index}-02-03', 'place_raw': '',
            'source_url': f'https://www.wikidata.org/wiki/Q{index}',
            'timezone': 'Asia/Shanghai', 'longitude': None, 'latitude': None}


def plan(count=3, requested=2):
    people = [person(i) for i in range(1, count + 1)]
    return build_plan({'seed': 17, 'eligibleCount': count, 'eligibleSha256': digest(people),
                       'selected': people}, {}, requested)


def entities(qids, rejected=()):
    return {qid: {'lastrevid': 123, 'claims': {'P569': [{'mainsnak': {'datavalue': {'value': {
        'precision': 9 if qid in rejected else 11,
        'time': f'+{1920 + int(qid[1:])}-02-03T00:00:00Z',
        'calendarmodel': 'http://www.wikidata.org/entity/Q1985727',
        'before': 0, 'after': 0,
    }}}}]}} for qid in qids}


class HoldoutVerificationTests(unittest.TestCase):
    def test_uses_first_qualified_in_frozen_order_without_changing_plan(self):
        original = plan()
        before = copy.deepcopy(original)
        with tempfile.TemporaryDirectory() as directory:
            result = verify_plan(original, directory, lambda qids: entities(qids, {'Q1'}))
            self.assertEqual([p['public_person_id'] for p in result['selected']], ['WD_Q2', 'WD_Q3'])
            self.assertEqual(result['sourceCheckedCount'], 3)
            self.assertEqual(result['sourceRejectedCount'], 1)
            self.assertTrue(all(p['sourceDateCheck']['accepted'] for p in result['selected']))
            with self.assertRaisesRegex(ValueError, 'already exists'):
                verify_plan(original, directory, lambda _: self.fail('No second fetch'))
        self.assertEqual(original, before)

    def test_changed_order_exclusions_and_cache_binding_are_rejected(self):
        altered = plan()
        altered['candidateOrder'].reverse()
        with self.assertRaisesRegex(ValueError, 'order'):
            validate_plan(altered)
        for key, value in (('excludedPublicIds', 'WD_Q1'),
                           ('excludedInputFingerprints', input_identity(person(1)))):
            altered = plan()
            altered[key].append(value)
            with self.assertRaisesRegex(ValueError, 'excluded'):
                validate_plan(altered)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, 'Incomplete'):
                verify_plan(plan(), directory, lambda _: {})
            altered = plan()
            altered['seed'] += 1
            with self.assertRaisesRegex(ValueError, 'different plan'):
                verify_plan(altered, directory, lambda _: self.fail('No fetch on mismatch'))
            (Path(directory) / 'verification-plan.json').unlink()
            with self.assertRaisesRegex(ValueError, 'no frozen verification binding'):
                verify_plan(plan(), directory, lambda _: self.fail('No fetch on orphan cache'))

    def test_interrupted_fetch_resumes_same_prefix_without_rechecking_or_redrawing(self):
        original = plan(52, 51)
        calls = []
        def interrupted(qids):
            calls.append(qids)
            if len(calls) == 2:
                raise RuntimeError('temporary failure')
            return entities(qids)
        with tempfile.TemporaryDirectory() as directory, patch('verify_public_holdout.time.sleep'):
            with self.assertRaisesRegex(RuntimeError, 'temporary failure'):
                verify_plan(original, directory, interrupted)
            cache = Path(directory) / 'source-checks.jsonl'
            prefix = cache.read_bytes()
            self.assertEqual(len(prefix.splitlines()), 50)
            resumed = []
            def resume(qids):
                resumed.extend(qids)
                return entities(qids)
            result = verify_plan(original, directory, resume)
            self.assertEqual(resumed, ['Q51', 'Q52'])
            self.assertEqual(len(result['selected']), 51)
            self.assertEqual(result['selected'][-1]['public_person_id'], 'WD_Q51')
            self.assertTrue(cache.read_bytes().startswith(prefix))
            self.assertEqual(len(cache.read_bytes().splitlines()), 51)

    def test_exhaustion_and_corrupt_prefix_do_not_silently_replace_people(self):
        with tempfile.TemporaryDirectory() as directory, patch('verify_public_holdout.time.sleep'):
            with self.assertRaisesRegex(RuntimeError, 'exhausted'):
                verify_plan(plan(), directory, lambda qids: entities(qids, set(qids)))
            self.assertFalse((Path(directory) / 'verified-cohort.json').exists())
            cache = Path(directory) / 'source-checks.jsonl'
            records = [json.loads(line) for line in cache.read_text(encoding='utf-8').splitlines()]
            records[0]['accepted'] = True
            cache.write_text('\n'.join(json.dumps(r) for r in records) + '\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'intact prefix'):
                verify_plan(plan(), directory, lambda _: self.fail('No fetch on corrupt cache'))


if __name__ == '__main__':
    unittest.main()
