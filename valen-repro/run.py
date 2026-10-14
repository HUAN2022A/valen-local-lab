"""Native/BF16/experimental bitsandbytes inference with upstream benchmark scoring."""
import argparse
from copy import deepcopy
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Valen'))
os.environ.setdefault('HF_HOME', str(ROOT / 'models/valen-hf'))


def versions():
    result = {}
    for name in ['torch', 'torchvision', 'transformers', 'peft', 'huggingface-hub',
                 'av', 'Pillow', 'numpy', 'bitsandbytes', 'accelerate']:
        try:
            result[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            result[name] = None
    return result


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def preflight():
    import torch
    result = {'python': sys.version, 'executable': sys.executable, 'platform': platform.platform(),
              'packages': versions(), 'cuda_available': torch.cuda.is_available(), 'cuda_runtime': torch.version.cuda}
    if torch.cuda.is_available():
        free, total = torch.cuda.mem_get_info()
        result.update(gpu=torch.cuda.get_device_name(), free_vram_bytes=free,
                      total_vram_bytes=total, bf16_supported=torch.cuda.is_bf16_supported())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['preflight', 'infer', 'evaluate'])
    parser.add_argument('--model', type=Path, default=ROOT / 'models/Valen-0.8B')
    parser.add_argument('--data', type=Path, help='Dataset directory or native JSONL')
    parser.add_argument('--output', type=Path, default=ROOT / 'Valen/output/repro/infer')
    parser.add_argument('--device', default='cuda:0', help='cpu or cuda:N; single-device execution')
    parser.add_argument('--dtype', choices=['native', 'bf16', 'fp32'], default='native')
    parser.add_argument('--quant', choices=['none', 'int8', 'nf4'], default='none')
    parser.add_argument('--execution', choices=['shared_state', 'question'], default='shared_state')
    parser.add_argument('--low-media', action='store_true', help='4-frame/resized diagnostic profile; not official benchmark settings')
    parser.add_argument('--request', type=Path, help='JSON request for infer; default is an English text example')
    parser.add_argument('--media-root', type=Path, default=Path('.'))
    args = parser.parse_args()
    if args.mode == 'preflight':
        preflight()
        return
    if args.mode == 'evaluate' and args.data is None:
        parser.error('--data is required for evaluate')
    if not args.model.is_dir():
        parser.error('Download the complete model with prepare.py first')
    if args.quant != 'none' and (not args.device.startswith('cuda') or args.dtype != 'bf16'):
        parser.error('Experimental quantization requires --device cuda:N --dtype bf16')
    if args.output.exists() and any(args.output.iterdir()):
        parser.error('Output directory must be new or empty; use a distinct output name')
    args.output.mkdir(parents=True, exist_ok=True)
    import torch
    from transformers import AutoModel, BitsAndBytesConfig
    if args.device.startswith('cuda'):
        if not torch.cuda.is_available():
            raise RuntimeError('CUDA is unavailable: verify CUDA torch installation or use --device cpu')
        torch.cuda.set_device(args.device)
        if args.dtype == 'bf16' and not torch.cuda.is_bf16_supported():
            raise RuntimeError('This GPU does not support BF16; use native CPU reference')
        torch.cuda.reset_peak_memory_stats()
    torch.manual_seed(0)
    torch.set_float32_matmul_precision('highest')
    torch.backends.cudnn.allow_tf32 = False
    torch.backends.cuda.matmul.allow_tf32 = False
    dtype = {'native': 'auto', 'bf16': torch.bfloat16, 'fp32': torch.float32}[args.dtype]
    options = dict(trust_remote_code=True, local_files_only=True, dtype=dtype,
                   attn_implementation='sdpa', output_loading_info=True)
    if args.quant != 'none':
        skip = ['head', 'backbone.visual']
        options['quantization_config'] = (BitsAndBytesConfig(load_in_8bit=True, llm_int8_skip_modules=skip)
            if args.quant == 'int8' else BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type='nf4',
                bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16,
                llm_int8_skip_modules=skip))
        # No automatic splitting: native runtime moves inputs using the first backbone parameter.
        options['device_map'] = {'': args.device}
    started = time.perf_counter()
    model, loading = AutoModel.from_pretrained(args.model.resolve(), **options)
    if any(loading.get(k) for k in ['missing_keys', 'unexpected_keys', 'mismatched_keys', 'error_msgs']):
        raise RuntimeError(f'Incomplete checkpoint load: {loading}')
    if args.quant == 'none':
        model = model.to(args.device)
    model.eval()
    if {p.dtype for p in model.head.parameters()} != {torch.float32}:
        raise RuntimeError('Trained Mixer must remain FP32; head precision/conversion check failed')
    if args.quant != 'none':
        import bitsandbytes as bnb
        quant_types = (bnb.nn.Linear4bit, bnb.nn.Linear8bitLt)
        quant_names = [n for n, module in model.named_modules() if isinstance(module, quant_types)]
        if not quant_names or any(n.startswith(('head', 'backbone.visual')) for n in quant_names):
            raise RuntimeError('Quantization failed or converted the protected Mixer/vision modules')
    else:
        quant_names = []
    if args.dtype == 'fp32':
        model.backbone_autocast_dtype = None  # Explicit full-FP32 diagnostic, distinct from native BF16 compute.
    if args.low_media:
        media = deepcopy(model.config.valen_media_kwargs)
        media['images_kwargs'] = {'size': {'shortest_edge': 32768, 'longest_edge': 131072}}
        media['videos_kwargs'] = {'num_frames': 4, 'fps': None,
                                 'size': {'shortest_edge': 32768, 'longest_edge': 262144}}
        model.config.valen_media_kwargs = media
    if args.device.startswith('cuda'):
        torch.cuda.synchronize()
    load_seconds = time.perf_counter() - started
    source = args.model / 'reproduction-source.json'
    data_source = (args.data if args.data and args.data.is_dir() else args.data.parent if args.data else None)
    metadata = dict(model=str(args.model.resolve()), dtype=args.dtype, quantization=args.quant,
                    attention='sdpa', execution=args.execution, device=args.device,
                    low_media=args.low_media, media_kwargs=model.config.valen_media_kwargs,
                    model_source=json.loads(source.read_text()) if source.exists() else None,
                    packages=versions(), python=sys.version, load_seconds=load_seconds,
                    backbone_autocast_dtype=str(model.backbone_autocast_dtype),
                    parameter_bytes=sum(p.numel() * p.element_size() for p in model.parameters()),
                    quantized_modules=quant_names,
                    git_revision=subprocess.check_output(['git', '-C', str(ROOT / 'Valen'), 'rev-parse', 'HEAD'], text=True).strip())
    if data_source and (data_source / 'reproduction-source.json').exists():
        metadata['data_source'] = json.loads((data_source / 'reproduction-source.json').read_text())
    write_json(args.output / 'run-config.json', metadata)
    started = time.perf_counter()
    try:
        with torch.inference_mode():
            if args.mode == 'evaluate':
                from evaluation.visualdecisionbench.evaluate import evaluate
                report = evaluate(model, args.data, args.output, args.device, args.execution)
            else:
                request = json.loads(args.request.read_text(encoding='utf-8')) if args.request else {
                    'state': 'A cat is on the sofa.', 'questions': {
                    'animal': {'type': 'choice', 'instructions': 'Which animal is present?',
                               'criteria': {'cat': 'A cat', 'dog': 'A dog'}},
                    'on_sofa': {'type': 'noul', 'instructions': 'The cat is on the sofa.'}}}
                report = model.predict(request, media_root=args.media_root, execution=args.execution)
                print(json.dumps(report, ensure_ascii=False, allow_nan=False), flush=True)
        if args.device.startswith('cuda'):
            torch.cuda.synchronize()
            metadata.update(peak_allocated_bytes=torch.cuda.max_memory_allocated(),
                            peak_reserved_bytes=torch.cuda.max_memory_reserved(),
                            gpu=torch.cuda.get_device_name())
        metadata.update(run_seconds=time.perf_counter() - started, status='complete')
        report['reproduction'] = metadata
        write_json(args.output / ('metrics.json' if args.mode == 'evaluate' else 'inference.json'), report)
    except Exception as exc:
        write_json(args.output / 'failure.json', dict(status='failed', error_type=type(exc).__name__,
                   error=str(exc), run_seconds=time.perf_counter() - started))
        raise  # Never skip failed records or emit a successful partial benchmark.


if __name__ == '__main__':
    main()
