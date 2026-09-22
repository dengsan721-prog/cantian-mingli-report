"""Freeze unseen public candidates without generating or scoring their reports."""
import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

from evaluate_scale import ROOT, digest, sample_cohort
from report_engine import normalize_input


def input_identity(person):
    year, month, day = map(int, person['date_standard'].split('-'))
    data = normalize_input({
        'name': person['primary_name'], 'gender': person['gender'], 'calendarType': 'solar',
        'year': year, 'month': month, 'day': day, 'birthplace': person.get('place_raw') or '',
        'timezone': person.get('timezone'), 'longitude': person.get('longitude'),
        'latitude': person.get('latitude'), 'timeText': '', 'calendarVerified': False,
        'timeStandardVerified': False, 'events': [],
    })
    return digest({key: data[key] for key in ('gender', 'solarDate', 'timeText', 'events')} |
                  {'place': data.get('resolvedPlace') or data['birthplace']})


def build_plan(pool, prior, count):
    excluded_ids, excluded_inputs = set(), set()
    for cohort in prior.values():
        for person in cohort['selected']:
            excluded_ids.add(person['public_person_id'])
            excluded_inputs.add(input_identity(person))
    candidates = [p for p in pool['selected']
                  if p['public_person_id'] not in excluded_ids and input_identity(p) not in excluded_inputs]
    if count < 2 or len(candidates) < count:
        raise ValueError(f'Requested {count}; unseen eligible candidates: {len(candidates)}')
    return {
        'status': 'frozen_candidates_not_source_verified_or_evaluated',
        'seed': pool['seed'], 'requestedSampleSize': count,
        'sourcePoolSha256': pool['eligibleSha256'], 'sourcePoolCount': pool['eligibleCount'],
        'excludedPublicRecordCount': len(excluded_ids), 'excludedInputCount': len(excluded_inputs),
        'excludedPublicIds': sorted(excluded_ids), 'excludedInputFingerprints': sorted(excluded_inputs),
        'excludedCohorts': {name: digest(cohort) for name, cohort in sorted(prior.items())},
        'remainingCandidateCount': len(candidates), 'candidateOrder': candidates,
        'candidateOrderSha256': digest(candidates),
        'selectionPolicy': f'Keep this random order; after live source qualification take the first {count} eligible records. Do not generate or inspect narrative outcomes to select records.',
        'scope': 'Excludes all frozen development cohort IDs and equivalent known narrative inputs. Earlier ten-person public fixtures are excluded by sample_cohort. No source verification or independent holdout performance is claimed yet.',
        'releaseCondition': 'Freeze the candidate implementation before generating this holdout. Preserve all failures; any tuning after viewing results requires a new independent holdout.',
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--count', type=int, default=100)
    parser.add_argument('--seed', type=int, default=20260922)
    args = parser.parse_args()
    path = args.output / 'holdout-plan.json'
    if path.exists():
        raise ValueError('Holdout plan already frozen; do not replace it with a new draw')
    evaluations = ROOT.parent / 'mingli-system/evaluations'
    files = sorted(evaluations.glob('*/cohort.json'))
    if not files:
        raise ValueError('No development cohort exclusion evidence found')
    prior = {str(file.relative_to(evaluations)): json.loads(file.read_text(encoding='utf-8')) for file in files}
    database = ROOT.parent / 'mingli-system/data/mingli_validation.db'
    size = sample_cohort(database, 2, args.seed)['eligibleCount']
    plan = build_plan(sample_cohort(database, size, args.seed), prior, args.count)
    plan['frozenAt'] = datetime.now().astimezone().isoformat()
    plan['preparationScriptSha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(plan, stream, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in plan.items() if k not in (
        'candidateOrder', 'excludedPublicIds', 'excludedInputFingerprints', 'excludedCohorts')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
