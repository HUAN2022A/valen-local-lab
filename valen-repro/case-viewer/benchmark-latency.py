"""Measure single-question API latency using three inputs per modality."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import mimetypes
from pathlib import Path
import statistics
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4


HERE = Path(__file__).resolve().parent


def get(base, path):
    with urlopen(base + path, timeout=30) as response:
        return json.load(response)


def infer(base, item, data_root):
    boundary = uuid4().hex
    body = bytearray()
    for name, value in item['fields'].items():
        body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    if item.get('media_path'):
        path = (data_root / item['media_path']).resolve()
        if data_root.resolve() not in path.parents:
            raise ValueError('Media path outside data root')
        body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="media_file"; filename="{path.name}"\r\nContent-Type: {mimetypes.guess_type(path.name)[0] or "application/octet-stream"}\r\n\r\n'.encode())
        body.extend(path.read_bytes())
        body.extend(b'\r\n')
    body.extend(f'--{boundary}--\r\n'.encode())
    started = time.perf_counter()
    with urlopen(Request(base + '/api/infer', data=body,
                        headers={'Content-Type': f'multipart/form-data; boundary={boundary}'}), timeout=300) as response:
        result = json.load(response)
    return result, time.perf_counter() - started


def media_inputs(base, modality):
    rows = get(base, '/api/cases?' + urlencode({'modality': modality, 'task': 'choice', 'limit': 100}))['items']
    selected, records = [], set()
    for row in rows:
        if row['record_index'] in records:
            continue
        detail = get(base, '/api/cases/' + row['id'])
        if not detail.get('media_path'):
            continue
        records.add(row['record_index'])
        selected.append({'id': row['id'], 'media_path': detail['media_path'], 'fields': {
            'state_text': detail['state_text'], 'instructions': detail['question'], 'question_type': 'choice',
            'criteria': '\n'.join(f'{key} | {value}' for key, value in detail['criteria'].items())}})
        if len(selected) == 3:
            return selected
    raise ValueError(f'Need three distinct {modality} media inputs')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8892')
    parser.add_argument('--data-root', type=Path, default=HERE.parents[1] / 'Valen/data/VisualDecisionBench')
    parser.add_argument('--output', type=Path, default=HERE / 'latency-report.json')
    parser.add_argument('--repeats', type=int, default=3)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error('--repeats must be positive')
    base = args.url.rstrip('/')
    status = get(base, '/api/model/status')
    cases = [
        ('cat', 'A cat is sitting on a blue sofa.', 'Which animal is on the sofa?', 'cat | Cat\ndog | Dog\nbird | Bird'),
        ('refund', 'The customer requests a refund for a duplicate charge.', 'Which department should handle this?', 'billing | Billing\ntech | Technical support\nsales | Sales'),
        ('rain', 'It is raining. Mei opens an umbrella before going outside.', 'What does Mei use?', 'umbrella | Umbrella\nhat | Hat\nbag | Bag'),
    ]
    inputs = {'text': [{'id': name, 'fields': {'state_text': state, 'instructions': question,
                         'question_type': 'choice', 'criteria': criteria}} for name, state, question, criteria in cases],
              'image': media_inputs(base, 'image'), 'video': media_inputs(base, 'video')}
    report = {'schema_version': 1, 'measured_at': datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds'),
              'scope': 'Single-question Choice requests; media preprocessing and synchronized inference included. Model loading, queue wait, upload and HTTP overhead excluded from inference_seconds.',
              'method': 'Three distinct inputs per modality, one warmup request per modality, then three rounds by default. Small local sample; input lengths and media complexity differ.',
              'model_was_loaded': status['phase'] == 'ready', 'modalities': {}, 'profile': {}, 'status': 'running'}
    try:
        for modality, items in inputs.items():
            warmup, wall = infer(base, items[0], args.data_root)
            profile = warmup['profile']
            report['profile'] = {key: profile.get(key) for key in ('device', 'dtype', 'quant', 'low_media', 'load_seconds')}
            report['profile']['gpu'] = (profile.get('gpu') or {}).get('name')
            entry = {'distinct_inputs': len(items), 'warmup_inference_seconds': warmup['elapsed_seconds'],
                     'warmup_request_seconds': wall, 'samples': []}
            report['modalities'][modality] = entry
            print(f'{modality}: warmup {warmup["elapsed_seconds"]:.3f}s', flush=True)
            for repeat in range(args.repeats):
                for item in items:
                    result, wall = infer(base, item, args.data_root)
                    entry['samples'].append({'input_id': item['id'], 'repeat': repeat + 1,
                                             'inference_seconds': result['elapsed_seconds'], 'request_seconds': wall})
                    print(f'{modality}: {len(entry["samples"])} / {len(items) * args.repeats}: {result["elapsed_seconds"]:.3f}s', flush=True)
            values = [sample['inference_seconds'] for sample in entry['samples']]
            entry.update(sample_count=len(values), mean_seconds=statistics.mean(values), median_seconds=statistics.median(values),
                         min_seconds=min(values), max_seconds=max(values))
        report['status'] = 'complete'
    except Exception as exc:
        report['status'] = 'failed'
        report['error'] = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix('.tmp')
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        temporary.replace(args.output)


if __name__ == '__main__':
    main()
