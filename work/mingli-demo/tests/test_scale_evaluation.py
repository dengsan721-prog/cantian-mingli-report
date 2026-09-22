import random
import sqlite3
import sys
import tempfile
import unittest
import weakref
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from evaluate_scale import encode_sets, overlap, pairwise_jaccards, sample_cohort
from verify_scale_cohort import verify_birth


class ScaleEvaluationTests(unittest.TestCase):
    def test_source_precision_cannot_be_inferred_from_january_first(self):
        value = {'time': '+2001-01-01T00:00:00Z', 'precision': 9,
                 'calendarmodel': 'http://www.wikidata.org/entity/Q1985727', 'before': 0, 'after': 0}
        entity = {'claims': {'P569': [{'rank': 'normal', 'mainsnak': {'datavalue': {'value': value}}}]}}
        self.assertFalse(verify_birth(entity, '2001-01-01')[0])
        value['precision'] = 11
        self.assertTrue(verify_birth(entity, '2001-01-01')[0])
        value['calendarmodel'] = 'http://www.wikidata.org/entity/Q1985786'
        self.assertFalse(verify_birth(entity, '2001-01-01')[0])
        self.assertFalse(verify_birth({}, '2001-01-01')[0])

    def test_bitsets_equal_exact_set_metrics(self):
        rng = random.Random(51)
        sets = [set(), {'中文片段'}, {'中文片段'}]
        sets += [set(rng.sample([f'片段{i}' for i in range(500)], rng.randrange(1, 400))) for _ in range(20)]
        bits, sizes = encode_sets(sets)
        for i, left in enumerate(sets):
            for j, right in enumerate(sets):
                common = len(left & right)
                self.assertEqual(overlap(bits[i], bits[j], sizes[i], sizes[j]),
                                 (common / max(1, len(left | right)), common / max(1, min(len(left), len(right)))))

    def test_bitsets_accept_one_shot_stream_with_growing_vocabulary(self):
        sets = [set(), {"早期共同片段"}, {f"新增片段{i}" for i in range(1000)},
                {"早期共同片段", "新增片段999"}, set(), {"最后片段"}]
        bits, sizes = encode_sets(values for values in sets)
        self.assertEqual(sizes, list(map(len, sets)))
        self.assertEqual(len(bits), len(sets))
        for i, left in enumerate(sets):
            for j, right in enumerate(sets):
                common = len(left & right)
                self.assertEqual(overlap(bits[i], bits[j], sizes[i], sizes[j]),
                                 (common / max(1, len(left | right)), common / max(1, min(len(left), len(right)))))
        self.assertEqual(encode_sets(iter(())), ([], []))

    def test_staged_jaccards_equal_raw_sets_in_exact_pair_order(self):
        rng = random.Random(538)
        universe = [f"中文七字片段{i}" for i in range(400)]
        sets = [set(), set(universe[:20]), {universe[0]}, {universe[0]}]
        sets += [set(rng.sample(universe, rng.randrange(1, 300))) for _ in range(60)]
        scores = pairwise_jaccards(values for values in sets)
        expected = [len(left & right) / max(1, len(left | right))
                    for i, left in enumerate(sets) for right in sets[i + 1:]]
        self.assertEqual(scores.tolist(), expected)
        self.assertEqual(str(scores.dtype), 'float64')
        self.assertIn(.05, scores.tolist())
        self.assertEqual(pairwise_jaccards(iter(())).tolist(), [])
        self.assertEqual(pairwise_jaccards(iter([set()])).tolist(), [])

    def test_staged_jaccards_release_encoded_corpus_before_returning(self):
        class TrackedCorpus(list):
            pass

        refs = []

        def tracked_encode(values):
            encoded, sizes = encode_sets(values)
            tracked = TrackedCorpus(encoded)
            refs.append(weakref.ref(tracked))
            return tracked, sizes

        with patch('evaluate_scale.encode_sets', side_effect=tracked_encode):
            scores = pairwise_jaccards(iter([{'甲'}, {'甲', '乙'}, {'丙'}]))
        self.assertEqual(scores.tolist(), [.5, 0, 0])
        self.assertEqual(len(refs), 1)
        self.assertIsNone(refs[0]())

    def test_staged_full_scores_preserve_body_and_containment_columns(self):
        body_sets = [set(), {'甲'}, {'甲', '乙'}, {'乙'}, {'甲'}]
        full_sets = [body | {f'标题{i % 2}', '共同注释'} for i, body in enumerate(body_sets)]
        full_scores = pairwise_jaccards(iter(full_sets))
        body, sizes = encode_sets(iter(body_sets))
        k = 0
        for i in range(len(body_sets)):
            for j in range(i + 1, len(body_sets)):
                score, contained = overlap(body[i], body[j], sizes[i], sizes[j])
                shared = len(body_sets[i] & body_sets[j])
                actual = (score, contained, float(full_scores[k]))
                expected = (shared / max(1, len(body_sets[i] | body_sets[j])),
                            shared / max(1, min(len(body_sets[i]), len(body_sets[j]))),
                            len(full_sets[i] & full_sets[j]) / len(full_sets[i] | full_sets[j]))
                self.assertEqual(actual, expected)
                k += 1
        self.assertEqual(k, len(full_scores))

    def test_public_sampling_is_stable_unique_and_excludes_ineligible(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / 'fixture.db'
            with closing(sqlite3.connect(database)) as connection:
                connection.executescript((ROOT.parent / 'mingli-system/database/schema.sql').read_text(encoding='utf-8'))
                for i in range(10):
                    subject = f'WD_QTEST{i}'
                    connection.execute('INSERT INTO public_persons (public_person_id,primary_name,gender) VALUES (?,?,?)',
                                       (subject, f'测试{i}', 'male'))
                    connection.execute('''INSERT INTO birth_facts
                        (birth_fact_id,subject_type,subject_id,date_standard,date_precision,calendar_type,source_url)
                        VALUES (?, 'public_person', ?, ?, ?, 'solar', ?)''',
                        (f'BF{i}', subject, '1980-02-30' if i == 0 else '1980-02-10',
                         'year' if i == 1 else 'day', f'https://www.wikidata.org/wiki/QTEST{i}'))
                connection.commit()
            first = sample_cohort(database, 6, 123)
            self.assertEqual(first, sample_cohort(database, 6, 123))
            self.assertEqual(first['eligibleCount'], 8)
            self.assertEqual(len({r['public_person_id'] for r in first['selected']}), 6)
            with self.assertRaises(ValueError):
                sample_cohort(database, 9, 123)


if __name__ == '__main__':
    unittest.main()
