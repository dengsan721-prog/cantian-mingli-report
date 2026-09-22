"""Frozen public cohort, exact all-pairs audit; never writes application history."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import heapq
import json
import random
import sqlite3
import sys
from collections import Counter
from contextlib import closing
from datetime import date, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluate_wisdom import anonymize, clock_invariant, full_sections_text, implementation_manifest, report_html, shingles
from narrative_engine import narrative_text
from narrative_diversity import TARGET
from report_engine import WISDOM_MODEL_VERSION, generate_report


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def sample_cohort(database, count, seed):
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute("""
            SELECT p.public_person_id, p.primary_name, p.gender, b.birth_fact_id,
                   b.date_standard, b.place_raw, b.source_url, b.calendar_verification_status,
                   b.calendar_model, b.timezone, b.longitude, b.latitude, b.updated_at
            FROM public_persons p JOIN birth_facts b ON b.subject_id=p.public_person_id
            WHERE b.subject_type='public_person' AND b.date_precision='day'
              AND b.calendar_type='solar' AND b.date_standard BETWEEN '1920-01-01' AND '2007-12-31'
              AND p.gender IN ('male','female') AND b.source_url LIKE 'https://www.wikidata.org/%'
              AND b.conflict_group_id IS NULL
            ORDER BY p.public_person_id, b.birth_fact_id
        """).fetchall()
    prior_ids = set()
    for file in (ROOT / 'tests').glob('public_narrative_*.json'):
        for person in json.loads(file.read_text(encoding='utf-8'))['people']:
            prior_ids.add((person['name'], person['birthDate']))
    unique = {}
    for raw in rows:
        row = dict(raw)
        try:
            date.fromisoformat(row['date_standard'])
        except ValueError:
            continue
        if (row['primary_name'], row['date_standard']) in prior_ids:
            continue
        unique.setdefault(row['public_person_id'], row)
    eligible = sorted(unique.values(), key=lambda row: row['public_person_id'])
    if count > len(eligible) or count < 2:
        raise ValueError(f'Requested {count}; eligible public persons: {len(eligible)}')
    selected = random.Random(seed).sample(eligible, count)
    return {'seed': seed, 'sampleSize': count, 'eligibleCount': len(eligible),
            'eligibleSha256': digest(eligible), 'selected': selected,
            'method': 'Uniform sampling without replacement from a sorted local Wikidata-derived pool, frozen before generation.',
            'scope': 'Public-data narrative stress test, not representative population, fresh source verification, reader study or predictive validation. All hours withheld/unknown; no life outcomes supplied.'}


def encode_sets(sets):
    """Exact bit positions, no probabilistic hashing or collision approximation."""
    vocabulary = {}
    encoded, sizes = [], []
    for values in sets:
        positions = []
        for value in values:
            positions.append(vocabulary.setdefault(value, len(vocabulary)))
        # New bit positions never move old ones, so input sets can be streamed.
        packed = bytearray((len(vocabulary) + 7) // 8)
        for position in positions:
            packed[position // 8] |= 1 << (position % 8)
        encoded.append(int.from_bytes(packed, 'little'))
        sizes.append(len(values))
    return encoded, sizes


def overlap(left, right, na, nb):
    shared = (left & right).bit_count()
    return shared / max(1, na + nb - shared), shared / max(1, min(na, nb))


def pairwise_jaccards(sets):
    """Keep only pair scores after releasing this phase's large encoded corpus."""
    encoded, sizes = encode_sets(sets)
    count = len(encoded)
    scores = np.empty(count * (count - 1) // 2, dtype=np.float64)
    k = 0
    for i in range(count):
        for j in range(i + 1, count):
            scores[k] = overlap(encoded[i], encoded[j], sizes[i], sizes[j])[0]
            k += 1
        if (i + 1) % 100 == 0:
            print(f'Audited full-section overlap {k}/{len(scores)} exact pairs', flush=True)
    return scores


def summary(values):
    return {'mean': float(np.mean(values)), 'max': float(np.max(values)),
            'p50': float(np.quantile(values, .5)), 'p95': float(np.quantile(values, .95)),
            'p99': float(np.quantile(values, .99))}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--count', type=int, default=1000)
    parser.add_argument('--seed', type=int, default=20260921)
    parser.add_argument('--database', type=Path, default=ROOT.parent / 'mingli-system/data/mingli_validation.db')
    parser.add_argument('--verified-cohort', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--enforce-target', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if (args.output / 'cohort.json').exists():
        raise ValueError('Output already contains a frozen cohort; use a new output directory.')
    cohort = (json.loads(args.verified_cohort.read_text(encoding='utf-8')) if args.verified_cohort
              else sample_cohort(args.database, args.count, args.seed))
    if len(cohort['selected']) != args.count or len({p['public_person_id'] for p in cohort['selected']}) != args.count:
        raise ValueError('Cohort must contain exactly the requested number of distinct persons')
    if args.verified_cohort and not all(p.get('sourceDateCheck', {}).get('accepted') for p in cohort['selected']):
        raise ValueError('Source-checked cohort contains an unaccepted record')
    manifest = implementation_manifest()
    manifest['mingli-demo/scripts/evaluate_scale.py'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    manifest['mingli-demo/scripts/verify_scale_cohort.py'] = hashlib.sha256((Path(__file__).parent / 'verify_scale_cohort.py').read_bytes()).hexdigest()
    frozen = {'frozenAt': datetime.now().astimezone().isoformat(), 'cohortSha256': digest(cohort),
              'implementationManifest': manifest, **cohort}
    (args.output / 'cohort.json').write_text(json.dumps(frozen, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Frozen {args.count} of {cohort["eligibleCount"]} eligible persons', flush=True)
    reports, checks, errors = [], [], []
    with gzip.open(args.output / 'reports.jsonl.gz', 'wt', encoding='utf-8') as stream:
        for index, person in enumerate(cohort['selected']):
            year, month, day = map(int, person['date_standard'].split('-'))
            payload = {'name': person['primary_name'], 'gender': person['gender'], 'calendarType': 'solar',
                       'year': year, 'month': month, 'day': day, 'birthplace': person['place_raw'] or '',
                       'timezone': person['timezone'], 'longitude': person['longitude'], 'latitude': person['latitude'],
                       'timeText': '', 'calendarVerified': False, 'timeStandardVerified': False, 'events': []}
            try:
                generated = generate_report(payload, use_wisdom=True)
                repeated = generate_report({**payload, 'name': '匿名样本'}, use_wisdom=True)
                check = {'id': person['public_person_id'],
                         'renameInvariant': generated['report']['sections'] == repeated['report']['sections'],
                         'unknownHourPreserved': generated['chart']['hour_pillar'] is None,
                         'clockInvariant': clock_invariant(payload, generated)}
                report = anonymize(generated['report'], [person['primary_name']])
                reports.append(report)
                checks.append(check)
                stream.write(json.dumps({'id': person['public_person_id'], 'payload': payload, 'report': report, 'checks': check}, ensure_ascii=False) + '\n')
            except Exception as error:
                errors.append({'id': person['public_person_id'], 'error': str(error), 'errorType': type(error).__name__})
            if (index + 1) % 50 == 0:
                print(f'Generated and stability-checked {index + 1}/{args.count}', flush=True)
    (args.output / 'checks.json').write_text(json.dumps({'checks': checks, 'errors': errors}, ensure_ascii=False, indent=2), encoding='utf-8')
    if errors:
        raise RuntimeError(f'{len(errors)} frozen samples failed; no replacements or partial-cohort pass permitted.')

    full_scores = pairwise_jaccards(shingles(full_sections_text(r)) for r in reports)
    body, body_sizes = encode_sets(shingles(narrative_text(r)) for r in reports)
    fragments = [{f for s in r['sections'] for f in s.get('narrativeEvidence', {}).get('fragmentIds', [])} for r in reports]
    judgments = [{(c['id'], c['claim']) for c in r.get('claims', []) if c.get('confidence') != '计算结果'} for r in reports]
    pair_count = args.count * (args.count - 1) // 2
    names = ['jaccard7', 'containment7', 'fullSectionsJaccard7', 'sharedFragmentFraction', 'sharedJudgmentFraction']
    values = np.zeros((pair_count, len(names)), dtype=np.float64)
    nearest = np.zeros(args.count)
    worst = []
    topic_collisions = Counter()
    k = 0
    with gzip.open(args.output / 'pairs.csv.gz', 'wt', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['left', 'right', *names])
        for i in range(args.count):
            for j in range(i + 1, args.count):
                score, contained = overlap(body[i], body[j], body_sizes[i], body_sizes[j])
                complete = float(full_scores[k])
                common_fragments = fragments[i] & fragments[j]
                row = [score, contained, complete,
                       len(common_fragments) / max(1, min(len(fragments[i]), len(fragments[j]))),
                       len(judgments[i] & judgments[j]) / max(1, min(len(judgments[i]), len(judgments[j])))]
                values[k] = row
                writer.writerow([cohort['selected'][i]['public_person_id'], cohort['selected'][j]['public_person_id'], *row])
                nearest[i] = max(nearest[i], score)
                nearest[j] = max(nearest[j], score)
                if len(worst) < 20:
                    heapq.heappush(worst, (score, i, j))
                elif score > worst[0][0]:
                    heapq.heapreplace(worst, (score, i, j))
                if score >= TARGET:
                    topic_collisions.update(common_fragments)
                k += 1
            if (i + 1) % 100 == 0:
                print(f'Audited {k}/{pair_count} exact pairs', flush=True)
    metrics = {name: summary(values[:, column]) for column, name in enumerate(names)}
    failed_pairs = int(np.count_nonzero(values[:, 0] >= TARGET))
    stable = all(all(v for key, v in c.items() if key != 'id') for c in checks)
    top_pairs = [{'left': cohort['selected'][i]['public_person_id'], 'right': cohort['selected'][j]['public_person_id'],
                  'jaccard7': score, 'leftIndex': i, 'rightIndex': j} for score, i, j in sorted(worst, reverse=True)]
    lexical_passed = failed_pairs == 0 and stable
    formal_model = "candidate" not in WISDOM_MODEL_VERSION
    result = {'evaluatedAt': datetime.now().astimezone().isoformat(), 'modelVersion': WISDOM_MODEL_VERSION,
              'sampleSize': args.count, 'pairCount': k, 'cohortSha256': frozen['cohortSha256'],
              'metrics': metrics, 'lexicalTarget': TARGET, 'failedPairCount': failed_pairs, 'failedPairFraction': failed_pairs / pair_count,
              'personsWithFailingNeighbor': int(np.count_nonzero(nearest >= TARGET)), 'nearestNeighbor': summary(nearest),
              'checksPassed': stable, 'lexicalTargetPassed': lexical_passed, 'releaseReady': lexical_passed and formal_model,
              'worstPairs': top_pairs, 'frequentSharedFragmentsInFailures': topic_collisions.most_common(30),
              'coverage': {'birthDecades': dict(Counter(p['date_standard'][:3] + '0s' for p in cohort['selected'])),
                           'gender': dict(Counter(p['gender'] for p in cohort['selected']))},
              'sourceScope': cohort['scope'],
              'limits': ['Source checks, when present, confirm Wikidata structured dates only, not independent documentary truth; calendar verification remains false.',
                         'No birth hours or known accomplishments are inferred. No real application records are created.',
                         'Seven-character set overlap is not semantic similarity or predictive accuracy.',
                         'Shared judgment/fragment IDs are proxies; no semantic model or human blind reader study.',
                         'Release readiness here covers this lexical-stability gate only; it is not predictive validation.']}
    (args.output / 'metrics.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    table = '\n'.join(f'|{name}|{m["mean"]:.2%}|{m["p95"]:.2%}|{m["max"]:.2%}|' for name, m in metrics.items())
    report = f'''# 千人公开样本叙事压力测试

固定抽样 {args.count} 人，全量比较 {k:,} 对，没有删除失败样本或反复抽取更好结果。

来源核验范围：{cohort['scope']}

|指标|均值|P95|最高|
|---|---:|---:|---:|
{table}

正文七字集合重复率未低于{TARGET:.0%}的配对：{failed_pairs:,} 对（{failed_pairs / pair_count:.2%}）。存在超标邻居的人数：{result['personsWithFailingNeighbor']}。稳定性检查：{stable}。

姓名已遮蔽，标点保留；完整章节指标另含标题、技术说明及注释。共同段落ID不会因改写变成新思想；共同判断比例不等于完整语义相似度。

这不是预测准确性或阅读趣味的验证。未知时刻不补全、已知成就不输入；评估不写入真实用户记录。若 modelVersion 不含 candidate 且 releaseReady 为 true，表示正式服务入口可使用该版本，但不代表预测已被证明。

cohort.json 为生成前冻结的名单与代码指纹；pairs.csv.gz 包含全部配对；reports.jsonl.gz 为可复核正文；checks.json 为逐人稳定性检查。
'''
    (args.output / 'README.md').write_text(report, encoding='utf-8')
    links = []
    for index in sorted({p[key] for p in top_pairs for key in ('leftIndex', 'rightIndex')}):
        p = cohort['selected'][index]
        person = {'name': p['primary_name'], 'birthDate': p['date_standard'], 'birthplace': p['place_raw'] or '未知', 'source': p['source_url']}
        filename = p['public_person_id'] + '.html'
        (args.output / filename).write_text(report_html(person, reports[index], WISDOM_MODEL_VERSION), encoding='utf-8')
        links.append(f'<li><a href="{filename}">{p["public_person_id"]}</a></li>')
    (args.output / 'index.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>千人测试高重复样本</title><h1>高重复配对试读</h1><p>测试场景不是人物真实经历或性格事实。指标见 metrics.json。</p><ul>' + ''.join(links) + '</ul></html>', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k not in ('worstPairs', 'frequentSharedFragmentsInFailures')}, ensure_ascii=False, indent=2), flush=True)
    if args.enforce_target and not result['lexicalTargetPassed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
