"""Reject incomplete predictions; optionally compare probability and accuracy drift."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Valen'))


def read_rows(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]


def validate(data, output):
    from valen.data.schema import candidates, target_distribution
    from valen.evaluation.metrics import summarize
    source = data / 'eval.jsonl' if data.is_dir() else data
    records = read_rows(source)
    expected = {}
    for i, record in enumerate(records):
        if set(record['targets']) != set(record['request']['questions']):
            raise ValueError(f'Missing targets in record {i}')
        for qid, spec in record['request']['questions'].items():
            keys = [key for key, _ in candidates(spec)]
            target = target_distribution(record['targets'][qid], keys)
            expected[i, qid] = (dict(zip(keys, target)), spec['type'], record.get('meta', {}))
    rows = read_rows(output / 'predictions.jsonl')
    counts = Counter((r['record_index'], r['qid']) for r in rows)
    if set(counts) != set(expected) or any(n != 1 for n in counts.values()):
        raise ValueError('Missing, duplicate, or extra prediction rows')
    for row in rows:
        target, kind, meta = expected[row['record_index'], row['qid']]
        if row['target'] != target or row['task'] != kind:
            raise ValueError('Target/task mismatch')
        if row['modality'] != meta.get('modality', 'unknown') or row['subset'] != meta.get('benchmark_subset', 'unknown'):
            raise ValueError('Modality/subset mismatch')
        probs = row['probabilities']
        if set(probs) != set(target) or any(not math.isfinite(v) or v < 0 or v > 1 for v in probs.values()):
            raise ValueError('Invalid probability vector')
        if not math.isclose(sum(probs.values()), 1.0, abs_tol=1e-5):
            raise ValueError('Probability sum is not one')
    report = json.loads((output / 'metrics.json').read_text(encoding='utf-8'))
    if report['records'] != len(records) or report['questions'] != len(expected):
        raise ValueError('Incorrect metrics counts')
    if report['metrics'] != summarize(rows):
        raise ValueError('Metrics do not match prediction rows')
    subsets = {s: summarize([r for r in rows if r['subset'] == s]) for s in {r['subset'] for r in rows}}
    if report['subsets'] != subsets:
        raise ValueError('Subset metrics do not match prediction rows')
    return rows, report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--compare', type=Path, help='Validated reference output on the SAME input JSONL')
    args = p.parse_args()
    rows, report = validate(args.data, args.output)
    result = {'verified': True, 'records': report['records'], 'questions': len(rows),
              'overall': report['metrics']['overall'],
              'subsets': {s: v['overall'] for s, v in report['subsets'].items()}}
    if args.compare:
        reference, baseline = validate(args.data, args.compare)
        ref = {(r['record_index'], r['qid']): r for r in reference}
        tv, flips = [], 0
        for row in rows:
            old = ref[row['record_index'], row['qid']]['probabilities']
            new = row['probabilities']
            tv.append(sum(abs(new[k] - old[k]) for k in old) / 2)
            flips += max(new, key=new.get) != max(old, key=old.get)
        result['comparison'] = {'mean_total_variation': sum(tv) / len(tv),
            'max_total_variation': max(tv), 'argmax_flip_questions': flips,
            'argmax_agreement': 1 - flips / len(tv),
            'accuracy_delta_pp': 100 * (report['metrics']['overall']['accuracy'] - baseline['metrics']['overall']['accuracy'])}
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
