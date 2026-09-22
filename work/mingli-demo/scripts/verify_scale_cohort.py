"""Check source date precision before selecting a new public narrative cohort."""
import argparse
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from evaluate_scale import ROOT, digest, sample_cohort


def verify_birth(entity, expected):
    statements = [s for s in entity.get('claims', {}).get('P569', []) if s.get('rank') != 'deprecated']
    values = [s.get('mainsnak', {}).get('datavalue', {}).get('value', {}) for s in statements]
    valid = bool(values) and all(isinstance(v, dict) and v.get('precision') == 11
                                and v.get('time', '').lstrip('+').split('T')[0] == expected
                                and v.get('calendarmodel', '').endswith('/Q1985727')
                                and not v.get('before') and not v.get('after') for v in values)
    return valid, values


def fetch(qids):
    query = urllib.parse.urlencode({'action': 'wbgetentities', 'ids': '|'.join(qids), 'props': 'claims', 'format': 'json', 'maxlag': '5'})
    request = urllib.request.Request('https://www.wikidata.org/w/api.php?' + query,
                                     headers={'User-Agent': 'MingliNarrativeAudit/0.1 (public birth-date precision audit)'})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                data = json.load(response)
            if 'error' in data or 'entities' not in data:
                raise RuntimeError(str(data.get('error', 'Missing entities')))
            return data['entities']
        except Exception:
            if attempt == 5:
                raise
            print(f'Source service busy; retrying after {60 * (attempt + 1)} seconds', flush=True)
            time.sleep(60 * (attempt + 1))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--count', type=int, default=1000)
    parser.add_argument('--seed', type=int, default=20260921)
    args = parser.parse_args()
    database = ROOT.parent / 'mingli-system/data/mingli_validation.db'
    size = sample_cohort(database, 2, args.seed)['eligibleCount']
    pool = sample_cohort(database, size, args.seed)
    args.output.mkdir(parents=True, exist_ok=True)
    plan_path = args.output / 'verification-plan.json'
    if plan_path.exists():
        plan = json.loads(plan_path.read_text(encoding='utf-8'))
        if plan['eligibleSha256'] != pool['eligibleSha256'] or plan['seed'] != args.seed:
            raise ValueError('Frozen plan no longer matches source pool or seed')
    else:
        plan_path.write_text(json.dumps(pool, ensure_ascii=False, indent=2), encoding='utf-8')
    cache_path = args.output / 'source-checks.jsonl'
    checked = {}
    if cache_path.exists():
        checked = {r['id']: r for r in map(json.loads, cache_path.read_text(encoding='utf-8').splitlines())}
    selected = []
    with cache_path.open('a', encoding='utf-8') as stream:
        for start in range(0, size, 50):
            batch = pool['selected'][start:start + 50]
            missing = [p for p in batch if p['public_person_id'] not in checked]
            entities = fetch([p['public_person_id'].removeprefix('WD_') for p in missing]) if missing else {}
            for person in batch:
                identifier = person['public_person_id']
                if identifier not in checked:
                    qid = identifier.removeprefix('WD_')
                    valid, values = verify_birth(entities.get(qid, {}), person['date_standard'])
                    record = {'id': identifier, 'source': person['source_url'], 'checkedAt': datetime.now().astimezone().isoformat(),
                              'expectedDate': person['date_standard'], 'accepted': valid, 'birthValues': values,
                              'entityRevision': entities.get(qid, {}).get('lastrevid')}
                    checked[identifier] = record
                    stream.write(json.dumps(record, ensure_ascii=False) + '\n')
                    stream.flush()
                if checked[identifier]['accepted']:
                    selected.append({**person, 'sourceDateCheck': checked[identifier]})
                if len(selected) == args.count:
                    break
            print(f'Source checked {len(checked)}; accepted {len(selected)}/{args.count}', flush=True)
            if len(selected) == args.count:
                break
            time.sleep(.5)
    if len(selected) != args.count:
        raise RuntimeError(f'Only {len(selected)} source-qualified dates; no synthetic replacements permitted')
    cohort = {**pool, 'sampleSize': len(selected), 'selected': selected,
              'method': f'Fixed random candidate order, accept first {args.count} passing live source-date criteria before generating any new reports; no selection by report similarity.',
              'scope': 'Wikidata structured date precision=11, Gregorian calendar, no nondeprecated conflicting/coarse birth claims, matching cached date. Not independent documentary verification or predictive validation.',
              'sourceCheckedCount': len(checked), 'sourceRejectedCount': sum(not r['accepted'] for r in checked.values()),
              'verificationPlanSha256': digest(pool),
              'precisionDocumentation': 'https://doc.wikimedia.org/Wikibase/master/php/docs_topics_json.html#time'}
    (args.output / 'verified-cohort.json').write_text(json.dumps(cohort, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
