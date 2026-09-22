"""Describe original-fragment and exact-paragraph reuse, not semantic uniqueness."""
import argparse
import csv
import gzip
import hashlib
import json
import re
from collections import Counter
from pathlib import Path


def topic_reuse(records, pairs, target=.05):
    indexed = {}
    for record in records:
        sections = {}
        for section in record['report']['sections']:
            paragraphs = [section['summary'], *section['scenes'], section['insight'], *section['items']]
            sections[section['id']] = (set(section['narrativeEvidence']['fragmentIds']),
                                       {re.sub(r'\s+', '', text) for text in paragraphs if text.strip()})
        indexed[record['id']] = sections
    topics = set(next(iter(indexed.values())))
    if any(set(sections) != topics for sections in indexed.values()):
        raise ValueError('Chapter coverage differs; do not silently omit missing topics')
    totals = {scope: {topic: Counter(sharedFragments=0, pairsWithSharedFragments=0,
                                    identicalParagraphs=0, pairsWithIdenticalParagraphs=0)
                      for topic in sorted(topics)} for scope in ('allPairs', 'failingPairs')}
    counts = Counter(allPairs=0, failingPairs=0)
    for pair in pairs:
        scopes = ['allPairs', 'failingPairs'] if float(pair['jaccard7']) >= target else ['allPairs']
        for scope in scopes:
            counts[scope] += 1
        for topic in topics:
            left_ids, left_paragraphs = indexed[pair['left']][topic]
            right_ids, right_paragraphs = indexed[pair['right']][topic]
            fragments = len(left_ids & right_ids)
            paragraphs = len(left_paragraphs & right_paragraphs)
            for scope in scopes:
                totals[scope][topic].update(sharedFragments=fragments, pairsWithSharedFragments=int(fragments > 0),
                                            identicalParagraphs=paragraphs, pairsWithIdenticalParagraphs=int(paragraphs > 0))
    return {'sampleSize': len(indexed), 'pairCounts': dict(counts), 'topics': totals}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    reports_path = args.directory / 'reports.jsonl.gz'
    pairs_path = args.directory / 'pairs.csv.gz'
    metrics = json.loads((args.directory / 'metrics.json').read_text(encoding='utf-8'))
    target = metrics.get('lexicalTarget', .05)
    with gzip.open(reports_path, 'rt', encoding='utf-8') as stream:
        records = [json.loads(line) for line in stream]
    with gzip.open(pairs_path, 'rt', encoding='utf-8', newline='') as stream:
        result = topic_reuse(records, csv.DictReader(stream), target=target)
    if (result['sampleSize'] != metrics['sampleSize'] or result['pairCounts']['allPairs'] != metrics['pairCount']
            or result['pairCounts']['failingPairs'] != metrics['failedPairCount']):
        raise ValueError('Supplemental audit does not match the original cohort or pair counts')
    result.update(modelVersion=metrics['modelVersion'], cohortSha256=metrics['cohortSha256'], lexicalTarget=target,
                  provenance={path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                              for path in (reports_path, pairs_path, Path(__file__))},
                  scope='Within each chapter, intersect original fragment IDs and whitespace-normalized paragraph sets. Counts accumulate per pair, not unique library paragraphs. All pairs and failing pairs disclosed separately; changing failing populations are not a causal comparison. No semantic or predictive accuracy claim.')
    (args.directory / 'topic-reuse.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
