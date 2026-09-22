"""Compare every pair in two audits of the exact same frozen cohort."""
import argparse
import csv
import gzip
import heapq
import json
from collections import Counter
from itertools import zip_longest
from pathlib import Path


def compare_runs(before, after):
    old = json.loads((before / 'metrics.json').read_text(encoding='utf-8'))
    new = json.loads((after / 'metrics.json').read_text(encoding='utf-8'))
    old_target, new_target = old.get('lexicalTarget', .05), new.get('lexicalTarget', .05)
    if old['cohortSha256'] != new['cohortSha256'] or old['pairCount'] != new['pairCount']:
        raise ValueError('Comparisons require the same frozen cohort and pair count')
    transitions = Counter()
    direction = Counter()
    worst = []
    count = 0
    with gzip.open(before / 'pairs.csv.gz', 'rt', encoding='utf-8', newline='') as left:
        with gzip.open(after / 'pairs.csv.gz', 'rt', encoding='utf-8', newline='') as right:
            for a, b in zip_longest(csv.DictReader(left), csv.DictReader(right)):
                if not a or not b or (a['left'], a['right']) != (b['left'], b['right']):
                    raise ValueError('Pair identities/order differ or a pair is missing')
                previous, current = float(a['jaccard7']), float(b['jaccard7'])
                delta = current - previous
                direction['improved' if delta < 0 else 'regressed' if delta > 0 else 'unchanged'] += 1
                transitions[f'{"fail" if previous >= old_target else "pass"}_to_{"fail" if current >= new_target else "pass"}'] += 1
                entry = (delta, a['left'], a['right'], previous, current)
                if len(worst) < 20:
                    heapq.heappush(worst, entry)
                elif delta > worst[0][0]:
                    heapq.heapreplace(worst, entry)
                count += 1
    if count != old['pairCount']:
        raise ValueError('Pair file count differs from declared audit count')
    return {'beforeModel': old['modelVersion'], 'afterModel': new['modelVersion'],
            'beforeLexicalTarget': old_target, 'afterLexicalTarget': new_target,
            'targetChanged': old_target != new_target,
            'cohortSha256': old['cohortSha256'], 'pairCount': count,
            'direction': dict(direction), 'gateTransitions': dict(transitions),
            'beforeMetrics': old['metrics'], 'afterMetrics': new['metrics'],
            'largestRegressions': [{'delta': d, 'left': i, 'right': j, 'before': a, 'after': b}
                                   for d, i, j, a, b in sorted(worst, reverse=True)],
            'note': 'Same persons, inputs and ordering. Direction measures actual score changes. Gate transitions use each archived target (legacy default 5%); changed targets are not prose improvements. A mean decrease does not imply every pair improved or passed.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('before', type=Path)
    parser.add_argument('after', type=Path)
    args = parser.parse_args()
    result = compare_runs(args.before, args.after)
    (args.after / 'comparison.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k not in ('beforeMetrics', 'afterMetrics', 'largestRegressions')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
