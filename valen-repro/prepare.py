"""Download pinned complete releases, validate assets, and prepare smoke subsets."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Valen'))
MODEL_REVISION = 'c2c481fcb319bd9ae834abc7c6373271710cf24e'
DATA_REVISION = '0c9e97031ca1dbc3e4f87640c03fc6c56dc8d685'
WEIGHT_SHA = '465714dd28702c4232d9233c2a2157d366967c541b2a27d9dadccc816304fd48'


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def write_json(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def prepare_subsets(folder):
    from valen.data.schema import read_jsonl
    rows = read_jsonl(folder / 'eval.jsonl')
    questions = sum(len(r['request']['questions']) for r in rows)
    if (len(rows), questions) != (1696, 9143):
        raise ValueError(f'Unexpected pinned dataset counts: {len(rows)}, {questions}')
    subsets = {}
    for modality, expected in [('image', (1402, 2000)), ('video', (294, 7143))]:
        selected = [r for r in rows if r['meta']['modality'] == modality]
        counts = (len(selected), sum(len(r['request']['questions']) for r in selected))
        if counts != expected:
            raise ValueError(f'{modality} counts: {counts}, expected {expected}')
        subsets[modality] = selected
    # Files remain alongside eval.jsonl: relative asset paths stay valid.
    for name, selected in [('smoke-image', subsets['image'][:2]),
                           ('smoke-video', subsets['video'][:2]),
                           ('pilot', subsets['image'][:10] + subsets['video'][:10]),
                           ('eval-image', subsets['image']),
                           ('eval-video', subsets['video'])]:
        with (folder / f'{name}.jsonl').open('w', encoding='utf-8') as out:
            for row in selected:
                out.write(json.dumps(row, ensure_ascii=False) + '\n')
    return {'records': len(rows), 'questions': questions, 'eval_sha256': sha256(folder / 'eval.jsonl')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-only', action='store_true')
    parser.add_argument('--data-only', action='store_true')
    parser.add_argument('--offline', action='store_true', help='Validate existing downloads; do not access Hub')
    args = parser.parse_args()
    if args.model_only and args.data_only:
        parser.error('Choose at most one of --model-only and --data-only')
    from huggingface_hub import snapshot_download
    if not args.data_only:
        folder = ROOT / 'models/Valen-0.8B'
        if not args.offline:
            snapshot_download('Valen-Team/Valen-0.8B', revision=MODEL_REVISION, local_dir=folder)
        if sha256(folder / 'model.safetensors') != WEIGHT_SHA:
            raise ValueError('Published model weight checksum mismatch')
        write_json(folder / 'reproduction-source.json', {'repo': 'Valen-Team/Valen-0.8B',
                   'revision': MODEL_REVISION, 'weight_sha256': WEIGHT_SHA})
        print('Model weight checksum verified', flush=True)
    if not args.model_only:
        folder = ROOT / 'Valen/data/VisualDecisionBench'
        if not args.offline:
            snapshot_download('Valen-Team/VisualDecisionBench', repo_type='dataset', revision=DATA_REVISION,
                              local_dir=folder, allow_patterns=['*.jsonl', '*.json', 'assets.zip',
                                                               'unpack_assets.py', 'README.md'])
        subprocess.run([sys.executable, str(folder / 'unpack_assets.py'), '--root', str(folder)], check=True)
        counts = prepare_subsets(folder)
        write_json(folder / 'reproduction-source.json', {'repo': 'Valen-Team/VisualDecisionBench',
                                                       'revision': DATA_REVISION, **counts})
        print(json.dumps(counts), flush=True)


if __name__ == '__main__':
    main()
