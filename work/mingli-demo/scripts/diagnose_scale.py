"""Separate identical known inputs from real cross-input narrative collisions."""
import argparse
import csv
import gzip
import heapq
import json
from collections import Counter, defaultdict
from pathlib import Path

from evaluate_scale import digest
from evaluate_wisdom import report_html
from report_engine import normalize_input


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    root = args.directory
    cohort = json.loads((root / 'cohort.json').read_text(encoding='utf-8'))
    target = json.loads((root / 'metrics.json').read_text(encoding='utf-8')).get('lexicalTarget', .05)
    with gzip.open(root / 'reports.jsonl.gz', 'rt', encoding='utf-8') as stream:
        reports = {r['id']: r for r in map(json.loads, stream)}
    identities = {}
    groups = defaultdict(list)
    for identifier, record in reports.items():
        data = normalize_input(record['payload'])
        identity = digest({key: data[key] for key in ('gender', 'solarDate', 'timeText', 'events')} |
                          {'place': data.get('resolvedPlace') or data['birthplace']})
        identities[identifier] = identity
        groups[identity].append(identifier)
    identical_count = distinct_count = distinct_failed = 0
    distinct_sum = 0
    highest = []
    distinct_neighbors = set()
    with gzip.open(root / 'pairs.csv.gz', 'rt', encoding='utf-8', newline='') as stream:
        for pair in csv.DictReader(stream):
            left, right = pair['left'], pair['right']
            score = float(pair['jaccard7'])
            if identities[left] == identities[right]:
                identical_count += 1
                continue
            distinct_count += 1
            distinct_sum += score
            if score >= target:
                distinct_failed += 1
                distinct_neighbors.update((left, right))
            if len(highest) < 20:
                heapq.heappush(highest, (score, left, right))
            elif score > highest[0][0]:
                heapq.heapreplace(highest, (score, left, right))
    shared_topics = Counter()
    worst = []
    for score, left, right in sorted(highest, reverse=True):
        left_sections = {s['id']: s for s in reports[left]['report']['sections']}
        overlaps = {}
        for section in reports[right]['report']['sections']:
            first = left_sections[section['id']].get('narrativeEvidence', {})
            second = section.get('narrativeEvidence', {})
            common = set(first.get('fragmentIds', [])) & set(second.get('fragmentIds', []))
            if common:
                overlaps[section['id']] = len(common)
                shared_topics[section['id']] += len(common)
        worst.append({'left': left, 'right': right, 'jaccard7': score, 'sharedFragmentsByChapter': overlaps})
    result = {'cohortSha256': cohort['cohortSha256'], 'lexicalTarget': target,
              'identicalKnownInputPairCount': identical_count,
              'identicalKnownInputGroups': [v for v in groups.values() if len(v) > 1],
              'distinctKnownInputPairCount': distinct_count, 'distinctKnownInputFailCount': distinct_failed,
              'distinctKnownInputMean': distinct_sum / max(1, distinct_count),
              'distinctKnownInputMax': max((p['jaccard7'] for p in worst), default=0),
              'distinctKnownInputPersonsWithFailingNeighbor': len(distinct_neighbors),
              'worstDistinctPairs': worst, 'sharedTopicsInTop20Pairs': shared_topics.most_common(),
              'note': 'Secondary diagnosis only: original all-pairs metrics remain unchanged. Identity uses the narrative-relevant normalized supplied fields; absent hours and events remain absent.'}
    (root / 'diagnosis.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    for identifier in {p[key] for p in worst for key in ('left', 'right')}:
        raw = next(p for p in cohort['selected'] if p['public_person_id'] == identifier)
        person = {'name': raw['primary_name'], 'birthDate': raw['date_standard'], 'birthplace': raw['place_raw'] or '未知', 'source': raw['source_url']}
        (root / (identifier + '.html')).write_text(report_html(person, reports[identifier]['report'], '跨输入高重复试读'), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
