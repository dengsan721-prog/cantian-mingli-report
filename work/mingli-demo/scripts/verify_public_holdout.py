"""Qualify a frozen holdout in its existing order; never generate narratives."""
import argparse
import hashlib
import json
import time
from datetime import datetime
from pathlib import Path

from evaluate_scale import digest
from freeze_public_holdout import input_identity
from verify_scale_cohort import fetch, verify_birth


def validate_plan(plan):
    if plan['status'] != 'frozen_candidates_not_source_verified_or_evaluated':
        raise ValueError('Expected an unevaluated frozen holdout plan')
    candidates = plan['candidateOrder']
    identifiers = [p['public_person_id'] for p in candidates]
    if (digest(candidates) != plan['candidateOrderSha256']
            or len(candidates) != plan['remainingCandidateCount']
            or len(set(identifiers)) != len(identifiers)):
        raise ValueError('Frozen candidate order or count does not match')
    if not 2 <= plan['requestedSampleSize'] <= len(candidates):
        raise ValueError('Insufficient frozen candidates; do not draw replacements')
    excluded_ids = set(plan['excludedPublicIds'])
    excluded_inputs = set(plan['excludedInputFingerprints'])
    if any(p['public_person_id'] in excluded_ids or input_identity(p) in excluded_inputs for p in candidates):
        raise ValueError('Holdout contains an excluded development person or known input')


def verify_plan(plan, output, fetcher=fetch):
    validate_plan(plan)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    target = output / 'verified-cohort.json'
    if target.exists():
        raise ValueError('Verified holdout already exists; do not overwrite or redraw')
    binding = {'holdoutPlanSha256': digest(plan),
               'candidateOrderSha256': plan['candidateOrderSha256'],
               'adapterSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'birthVerifierSha256': hashlib.sha256(Path(__file__).with_name('verify_scale_cohort.py').read_bytes()).hexdigest()}
    binding_path = output / 'verification-plan.json'
    cache_path = output / 'source-checks.jsonl'
    if binding_path.exists():
        if json.loads(binding_path.read_text(encoding='utf-8')) != binding:
            raise ValueError('Source cache belongs to a different plan or verifier')
    else:
        if cache_path.exists():
            raise ValueError('Source cache has no frozen verification binding')
        with binding_path.open('x', encoding='utf-8') as stream:
            json.dump(binding, stream, ensure_ascii=False, indent=2)

    candidates = plan['candidateOrder']
    cached = ([json.loads(line) for line in cache_path.read_text(encoding='utf-8').splitlines()]
              if cache_path.exists() else [])
    if len(cached) > len(candidates):
        raise ValueError('Source cache extends beyond the frozen plan')
    selected = []
    for index, record in enumerate(cached):
        person = candidates[index]
        values = record['birthValues']
        valid, _ = verify_birth({'claims': {'P569': [
            {'mainsnak': {'datavalue': {'value': value}}} for value in values
        ]}}, person['date_standard'])
        if (record['id'] != person['public_person_id'] or record['source'] != person['source_url']
                or record['expectedDate'] != person['date_standard'] or record['accepted'] is not valid):
            raise ValueError('Source cache is not an intact prefix of this candidate order')
        if len(selected) == plan['requestedSampleSize']:
            raise ValueError('Source cache continued after the requested sample was complete')
        if valid:
            selected.append({**person, 'sourceDateCheck': record})

    with cache_path.open('a', encoding='utf-8') as stream:
        for start in range(len(cached), len(candidates), 50):
            if len(selected) == plan['requestedSampleSize']:
                break
            batch = candidates[start:start + 50]
            qids = [p['public_person_id'].removeprefix('WD_') for p in batch]
            entities = fetcher(qids)
            if any(qid not in entities for qid in qids):
                raise RuntimeError('Incomplete source response; no missing records rejected or replaced')
            for person, qid in zip(batch, qids):
                valid, values = verify_birth(entities[qid], person['date_standard'])
                record = {'id': person['public_person_id'], 'source': person['source_url'],
                          'expectedDate': person['date_standard'], 'accepted': valid, 'birthValues': values,
                          'checkedAt': datetime.now().astimezone().isoformat(),
                          'entityRevision': entities[qid].get('lastrevid')}
                stream.write(json.dumps(record, ensure_ascii=False) + '\n')
                stream.flush()
                cached.append(record)
                if valid:
                    selected.append({**person, 'sourceDateCheck': record})
                if len(selected) == plan['requestedSampleSize']:
                    break
            print(f'Holdout source checked {len(cached)}; accepted {len(selected)}/{plan["requestedSampleSize"]}', flush=True)
            if len(selected) < plan['requestedSampleSize']:
                time.sleep(.5)
    if len(selected) != plan['requestedSampleSize']:
        raise RuntimeError('Frozen candidates exhausted; no replacement draw permitted')
    cohort = {'seed': plan['seed'], 'sampleSize': len(selected), 'selected': selected,
              'eligibleCount': len(candidates), 'eligibleSha256': plan['candidateOrderSha256'],
              'verificationPlanSha256': digest(plan), 'verificationImplementation': binding,
              'sourceChecksSha256': hashlib.sha256(cache_path.read_bytes()).hexdigest(),
              'excludedCohorts': plan['excludedCohorts'],
              'sourceCheckedCount': len(cached), 'sourceRejectedCount': sum(not r['accepted'] for r in cached),
              'method': 'First source-qualified records in the existing frozen holdout order; no resampling or narrative generation.',
              'scope': 'Wikidata structured Gregorian day-precision checks only, not independent archives, representative population, reader evaluation or predictive validation.'}
    with target.open('x', encoding='utf-8') as stream:
        json.dump(cohort, stream, ensure_ascii=False, indent=2)
    return cohort


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    cohort = verify_plan(json.loads(args.plan.read_text(encoding='utf-8')), args.output)
    print(json.dumps({key: cohort[key] for key in ('sampleSize', 'sourceCheckedCount', 'sourceRejectedCount', 'verificationPlanSha256')}, indent=2))


if __name__ == '__main__':
    main()
