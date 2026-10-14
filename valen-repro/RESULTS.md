# Valen-0.8B VisualDecisionBench 完整复现结果

运行日期：2026-10-13（Asia/Shanghai）
GPU：NVIDIA GeForce RTX 3060 Laptop GPU 6GB
源码：`95f06e8be99bd41e4a98aceddd3e4339c5a8e652`
模型：`Valen-Team/Valen-0.8B@c2c481fcb319bd9ae834abc7c6373271710cf24e`
数据：`Valen-Team/VisualDecisionBench@0c9e97031ca1dbc3e4f87640c03fc6c56dc8d685`

配置：发布模型原生 FP32 参数、backbone BF16 autocast、SDPA、`shared_state`、
官方图片像素预算、视频 16 帧、无量化、无低媒体降级。

## 核心结果

| 子集 | Records | Questions | Accuracy 分母 | 本机 Accuracy | 官方 Accuracy | 差值 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Image | 1,402 | 2,000 | 1,700 | 75.7647% | 75.94% | -0.1753 pp |
| Video | 294 | 7,143 | 7,143 | 79.0004% | 79.03% | -0.0296 pp |
| 合计 | 1,696 | 9,143 | 8,843 | 78.3784% | — | — |

Image 有 300 道软标签 Score 题不进入 accuracy；它们仍参与 NLL、Brier、Score MAE 与 RPS。
合计 Accuracy 是本机两个子集按 8,843 道硬标签题加权得到，官方未发布该合计值。

## 概率与序数指标

| 子集 | Brier | NLL | Score MAE | RPS |
| --- | ---: | ---: | ---: | ---: |
| Image | 0.316082 | 0.964581 | 1.329388 | 0.069313 |
| Video | 0.274436 | 0.516538 | 0.833645 | 0.138217 |

## 各题型 Accuracy

| 子集 | Choice | Noul | Score |
| --- | ---: | ---: | ---: |
| Image | 77.50%（1,200） | 76.50%（400） | 52.00%（100） |
| Video | 87.90%（5,000） | 84.7339%（714） | 44.9965%（1,429） |

括号内是硬标签 Accuracy 的有效题数。

## 性能与显存

| 子集 | 评测耗时 | 吞吐 | 峰值 allocated | 峰值 reserved |
| --- | ---: | ---: | ---: | ---: |
| Image | 792.34 秒（13:12） | 2.524 题/秒 | 4,658.5 MiB | 4,872 MiB |
| Video | 2,717.06 秒（45:17） | 2.629 题/秒 | 5,671.4 MiB | 9,026 MiB |
| 合计 | 3,509.39 秒（58:29） | 2.606 题/秒 | — | — |

Video 的 PyTorch `max_memory_reserved` 超过 6GB 物理显存；Windows WDDM 使用共享内存/分页
完成了运行。因此 6GB 可完成完整复现，但可能明显慢于拥有足够物理显存的 GPU，也不应把
9,026 MiB 与 `nvidia-smi` 的瞬时占用直接比较。

## 验收

- Image：1,402 条记录和 2,000 道题均恰好预测一次；
- Video：294 条记录和 7,143 道题均恰好预测一次；
- 目标、题型、模态、子集和候选键逐题匹配；
- 所有概率有限、范围为 `[0,1]`，每题概率和在 `1e-5` 误差内为 1；
- `metrics.json` 已从 `predictions.jsonl` 独立重算并完全一致；
- 两个子集均通过 `verify.py`，没有跳题、重复题或部分成功结果。

原始结果：

- `Valen/output/visualdecisionbench-image-native/metrics.json`
- `Valen/output/visualdecisionbench-image-native/predictions.jsonl`
- `Valen/output/visualdecisionbench-video-native/metrics.json`
- `Valen/output/visualdecisionbench-video-native/predictions.jsonl`
