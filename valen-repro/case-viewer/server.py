"""Local VisualDecisionBench explorer and Valen-0.8B inference server."""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import sys
import threading
import time
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
VALEN_ROOT = ROOT / "Valen"
DATA_ROOT = VALEN_ROOT / "data" / "VisualDecisionBench"
MODEL_ROOT = ROOT / "models" / "Valen-0.8B"
OUTPUT_ROOT = VALEN_ROOT / "output"
DIST_ROOT = HERE / "dist"
UPLOAD_ROOT = HERE / ".local-runtime" / "uploads"

sys.path.insert(0, str(VALEN_ROOT))
os.environ.setdefault("HF_HOME", str(ROOT / "models" / "valen-hf"))


def read_jsonl(path: Path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def argmax_key(values: dict[str, float] | None) -> str | None:
    if not values:
        return None
    return max(values, key=values.get)


def compact_text(value: str, limit: int = 120) -> str:
    value = " ".join(value.split())
    return value if len(value) <= limit else value[: limit - 1] + "…"


class CaseStore:
    def __init__(self) -> None:
        self.cases: list[dict[str, Any]] = []
        self.by_id: dict[str, dict[str, Any]] = {}
        self._load_subset(
            "image",
            DATA_ROOT / "eval-image.jsonl",
            OUTPUT_ROOT / "visualdecisionbench-image-native" / "predictions.jsonl",
        )
        self._load_subset(
            "video",
            DATA_ROOT / "eval-video.jsonl",
            OUTPUT_ROOT / "visualdecisionbench-video-native" / "predictions.jsonl",
        )
        self.summary = self._summary()

    def _load_subset(self, modality: str, data_path: Path, prediction_path: Path) -> None:
        if not data_path.exists() or not prediction_path.exists():
            raise FileNotFoundError(f"Missing benchmark input or prediction file: {data_path} / {prediction_path}")
        predictions = {(row["record_index"], row["qid"]): row for row in read_jsonl(prediction_path)}
        for record_index, record in enumerate(read_jsonl(data_path)):
            request = record["request"]
            questions = request["questions"]
            meta = record.get("meta", {})
            assets = record.get("assets", [])
            media_path = assets[0].get("path") if assets else None
            media_url = "/api/media/" + media_path.replace("\\", "/") if media_path else None
            state = request.get("state", "")
            state_text = ""
            if isinstance(state, str):
                state_text = state
            elif isinstance(state, dict):
                for message in state.get("messages", []):
                    for part in message.get("content", []):
                        if part.get("type") == "text":
                            state_text += ("\n" if state_text else "") + part.get("text", "")
            for qid, question in questions.items():
                pred = predictions.get((record_index, qid))
                if pred is None:
                    raise ValueError(f"Prediction missing for {modality} record {record_index}, {qid}")
                criteria = question.get("criteria", {})
                if isinstance(criteria, list):
                    criteria_map = {str(i): value for i, value in enumerate(criteria)}
                else:
                    criteria_map = {str(key): value for key, value in criteria.items()}
                target = pred.get("target", {})
                probabilities = pred.get("probabilities", {})
                answer = pred.get("answer", {})
                task = pred.get("task", question.get("type", "unknown"))
                if task == "choice":
                    predicted_key = answer.get("choice") or argmax_key(probabilities)
                elif task == "noul":
                    predicted_key = "true" if float(answer.get("noul", probabilities.get("true", 0))) >= 0.5 else "false"
                else:
                    predicted_key = argmax_key(probabilities)
                accuracy = pred.get("metrics", {}).get("accuracy")
                case_id = f"{modality}-{record_index}-{qid}"
                expected_key = argmax_key(target)
                item = {
                    "id": case_id,
                    "record_index": record_index,
                    "record_id": pred.get("record_id") or meta.get("benchmark_record_id"),
                    "qid": qid,
                    "task": task,
                    "modality": modality,
                    "source": meta.get("source") or meta.get("source_collection") or "unknown",
                    "domain": pred.get("domain") or meta.get("domain", "unknown"),
                    "language": pred.get("language") or meta.get("language_bucket", "unknown"),
                    "question": question.get("instructions", ""),
                    "question_short": compact_text(question.get("instructions", "")),
                    "state_text": state_text,
                    "criteria": criteria_map,
                    "target": target,
                    "expected_key": expected_key,
                    "probabilities": probabilities,
                    "answer": answer,
                    "predicted_key": predicted_key,
                    "metrics": pred.get("metrics", {}),
                    "correct": None if accuracy is None else bool(accuracy >= 0.5),
                    "media_path": media_path,
                    "media_url": media_url,
                    "meta": {
                        "benchmark": meta.get("benchmark"),
                        "subset": meta.get("benchmark_subset"),
                        "source": meta.get("source"),
                        "source_id": meta.get("source_id") or meta.get("video_id"),
                        "record_id": meta.get("record_id"),
                        "label_source": meta.get("label_source"),
                        "license": meta.get("license"),
                    },
                    "raw_input": {
                        "state": state,
                        "questions": {qid: question},
                        "assets": assets,
                    },
                    "raw_output": pred,
                }
                item["search"] = " ".join(
                    [str(item.get(key, "")) for key in ("record_id", "qid", "source", "domain", "question")]
                    + [json.dumps(criteria_map, ensure_ascii=False), str(predicted_key), str(expected_key)]
                ).lower()
                self.cases.append(item)
                self.by_id[case_id] = item

    def _summary(self) -> dict[str, Any]:
        scored = [case for case in self.cases if case["correct"] is not None]
        correct = sum(1 for case in scored if case["correct"])
        return {
            "questions": len(self.cases),
            "records": len({(case["modality"], case["record_index"]) for case in self.cases}),
            "image": sum(1 for case in self.cases if case["modality"] == "image"),
            "video": sum(1 for case in self.cases if case["modality"] == "video"),
            "choice": sum(1 for case in self.cases if case["task"] == "choice"),
            "noul": sum(1 for case in self.cases if case["task"] == "noul"),
            "score": sum(1 for case in self.cases if case["task"] == "score"),
            "hard_scored": len(scored),
            "hard_correct": correct,
            "accuracy": correct / len(scored) if scored else None,
        }

    def query(
        self,
        offset: int,
        limit: int,
        modality: str,
        task: str,
        result: str,
        search: str,
    ) -> dict[str, Any]:
        search = search.strip().lower()

        def keep(case: dict[str, Any]) -> bool:
            if modality != "all" and case["modality"] != modality:
                return False
            if task != "all" and case["task"] != task:
                return False
            if result == "correct" and case["correct"] is not True:
                return False
            if result == "wrong" and case["correct"] is not False:
                return False
            if result == "unscored" and case["correct"] is not None:
                return False
            return not search or search in case["search"]

        filtered = [case for case in self.cases if keep(case)]
        items = []
        for case in filtered[offset : offset + limit]:
            items.append({key: case[key] for key in (
                "id", "record_index", "record_id", "qid", "task", "modality", "source",
                "domain", "question_short", "predicted_key", "expected_key", "correct",
            )})
        return {"total": len(filtered), "offset": offset, "limit": limit, "items": items}


class ModelManager:
    def __init__(self, device: str, dtype: str, quant: str, low_media: bool) -> None:
        self.device = device
        self.dtype = dtype
        self.quant = quant
        self.low_media = low_media
        self.model = None
        self.lock = threading.Lock()
        self.state_lock = threading.Lock()
        self.phase = "unloaded"
        self.detail = "首次推理时加载模型"
        self.load_seconds: float | None = None
        self.last_error: str | None = None

    def status(self) -> dict[str, Any]:
        gpu = None
        try:
            import torch

            if torch.cuda.is_available():
                free, total = torch.cuda.mem_get_info()
                gpu = {
                    "name": torch.cuda.get_device_name(),
                    "free_bytes": free,
                    "total_bytes": total,
                    "allocated_bytes": torch.cuda.memory_allocated(),
                    "reserved_bytes": torch.cuda.memory_reserved(),
                }
        except Exception:
            pass
        with self.state_lock:
            return {
                "phase": self.phase,
                "detail": self.detail,
                "load_seconds": self.load_seconds,
                "last_error": self.last_error,
                "device": self.device,
                "dtype": self.dtype,
                "quant": self.quant,
                "low_media": self.low_media,
                "gpu": gpu,
            }

    def _set_state(self, phase: str, detail: str, error: str | None = None) -> None:
        with self.state_lock:
            self.phase = phase
            self.detail = detail
            self.last_error = error

    def load(self):
        if self.model is not None:
            return self.model
        import torch
        from transformers import AutoModel, BitsAndBytesConfig

        if self.device.startswith("cuda") and not torch.cuda.is_available():
            raise RuntimeError("CUDA 不可用，请检查 PyTorch/CUDA 环境或改用 --device cpu")
        if self.device.startswith("cuda"):
            torch.cuda.set_device(self.device)
            if self.dtype == "bf16" and not torch.cuda.is_bf16_supported():
                raise RuntimeError("当前 GPU 不支持 BF16")
        self._set_state("loading", "正在载入 Valen-0.8B")
        started = time.perf_counter()
        dtype = {"native": "auto", "bf16": torch.bfloat16, "fp32": torch.float32}[self.dtype]
        options: dict[str, Any] = {
            "trust_remote_code": True,
            "local_files_only": True,
            "dtype": dtype,
            "attn_implementation": "sdpa",
            "output_loading_info": True,
        }
        if self.quant != "none":
            skip = ["head", "backbone.visual"]
            options["quantization_config"] = (
                BitsAndBytesConfig(load_in_8bit=True, llm_int8_skip_modules=skip)
                if self.quant == "int8"
                else BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_use_double_quant=True,
                    bnb_4bit_compute_dtype=torch.bfloat16,
                    llm_int8_skip_modules=skip,
                )
            )
            options["device_map"] = {"": self.device}
        model, loading = AutoModel.from_pretrained(MODEL_ROOT.resolve(), **options)
        problems = {key: loading.get(key) for key in ("missing_keys", "unexpected_keys", "mismatched_keys", "error_msgs") if loading.get(key)}
        if problems:
            raise RuntimeError(f"模型权重加载不完整: {problems}")
        if self.quant == "none":
            model = model.to(self.device)
        model.eval()
        if self.dtype == "fp32":
            model.backbone_autocast_dtype = None
        if self.low_media:
            media = deepcopy(model.config.valen_media_kwargs)
            media["images_kwargs"] = {"size": {"shortest_edge": 32768, "longest_edge": 131072}}
            media["videos_kwargs"] = {
                "num_frames": 4,
                "fps": None,
                "size": {"shortest_edge": 32768, "longest_edge": 262144},
            }
            model.config.valen_media_kwargs = media
        self.model = model
        self.load_seconds = time.perf_counter() - started
        self._set_state("ready", f"模型已就绪 · 加载 {self.load_seconds:.1f} 秒")
        return model

    def predict(self, request: dict[str, Any], media_root: Path) -> tuple[dict[str, Any], float]:
        import torch

        with self.lock:
            try:
                model = self.load()
                self._set_state("running", "正在执行推理")
                started = time.perf_counter()
                with torch.inference_mode():
                    result = model.predict(request, media_root=media_root, execution="shared_state")
                if self.device.startswith("cuda"):
                    torch.cuda.synchronize()
                elapsed = time.perf_counter() - started
                self._set_state("ready", f"模型已就绪 · 上次推理 {elapsed:.2f} 秒")
                return result, elapsed
            except Exception as exc:
                if "out of memory" in str(exc).lower():
                    try:
                        torch.cuda.empty_cache()
                    except Exception:
                        pass
                self._set_state("error", "推理失败", f"{type(exc).__name__}: {exc}")
                raise

    def unload(self) -> None:
        import gc
        import torch

        with self.lock:
            self.model = None
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            self.load_seconds = None
            self._set_state("unloaded", "模型已卸载，显存已释放")


def parse_criteria(question_type: str, raw: str) -> dict[str, str] | list[str] | None:
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if question_type == "noul":
        return None
    if question_type == "score":
        if len(lines) < 2:
            raise HTTPException(400, "Score 类型至少需要两条评分标准")
        return lines
    if len(lines) < 2:
        raise HTTPException(400, "Choice 类型至少需要两个选项")
    result: dict[str, str] = {}
    for index, line in enumerate(lines):
        if "|" in line:
            key, description = (part.strip() for part in line.split("|", 1))
        else:
            key, description = chr(65 + index), line
        if not key or not description or key in result:
            raise HTTPException(400, "选项格式无效或键重复，请使用 A | 选项内容")
        result[key] = description
    return result


def create_app(args: argparse.Namespace) -> FastAPI:
    store = CaseStore()
    manager = ModelManager(args.device, args.dtype, args.quant, args.low_media)
    app = FastAPI(title="Valen Local Lab", docs_url=None, redoc_url=None)

    @app.get("/api/summary")
    def summary():
        return {"benchmark": store.summary, "model": manager.status()}

    @app.get("/api/cases")
    def cases(
        offset: int = Query(0, ge=0),
        limit: int = Query(30, ge=1, le=100),
        modality: str = Query("all", pattern="^(all|image|video)$"),
        task: str = Query("all", pattern="^(all|choice|noul|score)$"),
        result: str = Query("all", pattern="^(all|correct|wrong|unscored)$"),
        search: str = Query("", max_length=500),
    ):
        return store.query(offset, limit, modality, task, result, search)

    @app.get("/api/cases/{case_id}")
    def case_detail(case_id: str):
        case = store.by_id.get(case_id)
        if not case:
            raise HTTPException(404, "案例不存在")
        return {key: value for key, value in case.items() if key != "search"}

    @app.get("/api/media/{asset_path:path}")
    def media(asset_path: str):
        candidate = (DATA_ROOT / asset_path).resolve()
        root = DATA_ROOT.resolve()
        if root not in candidate.parents or not candidate.is_file():
            raise HTTPException(404, "媒体文件不存在")
        return FileResponse(candidate)

    @app.get("/api/model/status")
    def model_status():
        return manager.status()

    @app.post("/api/model/unload")
    def unload_model():
        manager.unload()
        return manager.status()

    @app.post("/api/infer")
    def infer(
        state_text: str = Form(""),
        instructions: str = Form(...),
        question_type: str = Form("choice"),
        criteria: str = Form(""),
        media_file: UploadFile | None = File(None),
    ):
        if question_type not in {"choice", "noul", "score"}:
            raise HTTPException(400, "question_type 仅支持 choice、noul、score")
        instructions = instructions.strip()
        if not instructions:
            raise HTTPException(400, "问题不能为空")
        parsed = parse_criteria(question_type, criteria)
        question: dict[str, Any] = {"type": question_type, "instructions": instructions}
        if parsed is not None:
            question["criteria"] = parsed
        saved: Path | None = None
        try:
            if media_file and media_file.filename:
                suffix = Path(media_file.filename).suffix.lower()
                image_suffixes = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
                video_suffixes = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
                if suffix not in image_suffixes | video_suffixes:
                    raise HTTPException(400, "仅支持常见图片或视频格式")
                UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
                saved = UPLOAD_ROOT / f"{uuid4().hex}{suffix}"
                with saved.open("wb") as output:
                    shutil.copyfileobj(media_file.file, output)
                content: list[dict[str, Any]] = []
                if state_text.strip():
                    content.append({"type": "text", "text": state_text.strip()})
                media_type = "image_url" if suffix in image_suffixes else "video_url"
                content.append({"type": media_type, media_type: {"url": saved.name}})
                state: Any = {"messages": [{"role": "user", "content": content}]}
            else:
                state = state_text.strip() or "Answer the question using the provided information."
            request = {"state": state, "questions": {"custom": question}}
            result, elapsed = manager.predict(request, UPLOAD_ROOT)
            return {
                "result": result,
                "elapsed_seconds": elapsed,
                "profile": manager.status(),
                "request": request,
            }
        except HTTPException:
            raise
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            if "out of memory" in str(exc).lower():
                message += "。显存不足：关闭其他 GPU 应用，或使用 -Precision bf16 / -Quantization int8 后重启。"
            raise HTTPException(500, message) from exc
        finally:
            if saved:
                saved.unlink(missing_ok=True)

    app.mount("/", StaticFiles(directory=DIST_ROOT, html=True), name="static")
    return app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8892)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--dtype", choices=("native", "bf16", "fp32"), default="bf16")
    parser.add_argument("--quant", choices=("none", "int8", "nf4"), default="none")
    parser.add_argument("--low-media", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    import uvicorn

    arguments = parse_args()
    uvicorn.run(create_app(arguments), host=arguments.host, port=arguments.port, log_level="info")
