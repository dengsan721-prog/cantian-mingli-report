import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_topic_reuse import topic_reuse


def record(identifier, paragraph, fragment):
    return {'id': identifier, 'report': {'sections': [
        {'id': 'example', 'summary': paragraph, 'scenes': [paragraph], 'insight': '', 'items': [],
         'narrativeEvidence': {'fragmentIds': [fragment]}}
    ]}}


class TopicReuseTests(unittest.TestCase):
    def test_explicit_six_percent_target_keeps_exact_boundary_failing(self):
        records = [record('a', '一段文字', 'original:1'), record('b', '一段文字', 'original:1'),
                   record('c', '一段文字', 'original:2')]
        pairs = [{'left': 'a', 'right': 'b', 'jaccard7': .055},
                 {'left': 'a', 'right': 'c', 'jaccard7': .06}]
        result = topic_reuse(records, pairs, target=.06)
        self.assertEqual(result['pairCounts'], {'allPairs': 2, 'failingPairs': 1})

    def test_all_pairs_and_strict_threshold_are_separate_and_duplicates_count_once(self):
        records = [record('a', '一段 文字', 'original:1'), record('b', '一段文字', 'original:1'),
                   record('c', '一段文字', 'original:2')]
        pairs = [{'left': 'a', 'right': 'b', 'jaccard7': '.049'},
                 {'left': 'a', 'right': 'c', 'jaccard7': '.05'},
                 {'left': 'b', 'right': 'c', 'jaccard7': '.06'}]
        result = topic_reuse(records, pairs)
        self.assertEqual(result['pairCounts'], {'allPairs': 3, 'failingPairs': 2})
        all_topic = result['topics']['allPairs']['example']
        failed_topic = result['topics']['failingPairs']['example']
        self.assertEqual(all_topic['sharedFragments'], 1)
        self.assertEqual(all_topic['identicalParagraphs'], 3)
        self.assertEqual(failed_topic['sharedFragments'], 0)
        self.assertEqual(failed_topic['identicalParagraphs'], 2)
        self.assertEqual(failed_topic['pairsWithIdenticalParagraphs'], 2)

    def test_paragraph_changes_do_not_create_new_original_fragments_or_mutate_reports(self):
        records = [record('a', '一种表达', 'original:1'), record('b', '另一种表达', 'original:1')]
        before = copy.deepcopy(records)
        result = topic_reuse(records, [{'left': 'a', 'right': 'b', 'jaccard7': 0}])
        topic = result['topics']['allPairs']['example']
        self.assertEqual(topic['sharedFragments'], 1)
        self.assertEqual(topic['identicalParagraphs'], 0)
        self.assertEqual(result['topics']['failingPairs']['example']['sharedFragments'], 0)
        self.assertEqual(records, before)

    def test_incomplete_chapter_coverage_is_not_silently_scored(self):
        records = [record('a', '甲', 'original:1'), record('b', '乙', 'original:2')]
        records[1]['report']['sections'][0]['id'] = 'different'
        with self.assertRaisesRegex(ValueError, 'coverage differs'):
            topic_reuse(records, [{'left': 'a', 'right': 'b', 'jaccard7': 0}])


if __name__ == '__main__':
    unittest.main()
