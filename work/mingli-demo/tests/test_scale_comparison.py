import csv
import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from compare_scale_runs import compare_runs


class ScaleComparisonTests(unittest.TestCase):
    def write_run(self, root, scores, cohort='same', target=None):
        root.mkdir()
        metrics = {'cohortSha256': cohort, 'pairCount': len(scores), 'modelVersion': root.name, 'metrics': {}}
        if target is not None:
            metrics['lexicalTarget'] = target
        (root / 'metrics.json').write_text(json.dumps(metrics), encoding='utf-8')
        with gzip.open(root / 'pairs.csv.gz', 'wt', encoding='utf-8', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(['left', 'right', 'jaccard7'])
            for i, score in enumerate(scores):
                writer.writerow(['a', str(i), score])

    def test_strict_boundary_and_both_directions_are_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            old, new = Path(directory) / 'old', Path(directory) / 'new'
            self.write_run(old, [.06, .02, .03, .08])
            self.write_run(new, [.04, .05, .03, .07])
            result = compare_runs(old, new)
            self.assertEqual(result['direction'], {'improved': 2, 'regressed': 1, 'unchanged': 1})
            self.assertEqual(result['gateTransitions'], {'fail_to_pass': 1, 'pass_to_fail': 1, 'pass_to_pass': 1, 'fail_to_fail': 1})
            self.assertEqual(result['largestRegressions'][0]['right'], '1')

    def test_different_cohorts_cannot_be_compared_as_paired_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            old, new = Path(directory) / 'old', Path(directory) / 'new'
            self.write_run(old, [.01])
            self.write_run(new, [.01], cohort='different')
            with self.assertRaises(ValueError):
                compare_runs(old, new)

    def test_changed_target_is_not_reported_as_prose_improvement(self):
        with tempfile.TemporaryDirectory() as directory:
            old, new = Path(directory) / 'old', Path(directory) / 'new'
            self.write_run(old, [.055, .06])
            self.write_run(new, [.055, .06], target=.06)
            result = compare_runs(old, new)
            self.assertTrue(result['targetChanged'])
            self.assertEqual(result['beforeLexicalTarget'], .05)
            self.assertEqual(result['afterLexicalTarget'], .06)
            self.assertEqual(result['direction'], {'unchanged': 2})
            self.assertEqual(result['gateTransitions'], {'fail_to_pass': 1, 'fail_to_fail': 1})


if __name__ == '__main__':
    unittest.main()
