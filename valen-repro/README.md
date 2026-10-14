# Valen ≤8GB GPU 推理与 VisualDecisionBench 复现

本目录是在 Windows 11、RTX 3060 Laptop 6GB 上实测过的可复现入口。它不会修改
`laya-learning` 的环境，而是用其 Python 3.11 解释器通过 `uv` 创建独立的
`Valen/.venv`。

## 已锁定的版本

- Valen 源码：`95f06e8be99bd41e4a98aceddd3e4339c5a8e652`
- Valen-0.8B：`c2c481fcb319bd9ae834abc7c6373271710cf24e`
- VisualDecisionBench：`0c9e97031ca1dbc3e4f87640c03fc6c56dc8d685`
- Python 3.11.14、PyTorch 2.6.0+cu124、Transformers 5.4.0
- 可选量化：bitsandbytes 0.49.2、accelerate 1.15.0

权重 SHA-256 固定为
`465714dd28702c4232d9233c2a2157d366967c541b2a27d9dadccc816304fd48`。
数据准备后应得到 1,696 条 state、9,143 道题和 1,693 个媒体文件；其中 Image 为
1,402 条/2,000 题，Video 为 294 条/7,143 题。

本机 9,143 题完整运行与独立校验结果见 [`RESULTS.md`](RESULTS.md)：Image
75.7647%，Video 79.0004%，总评测耗时 58 分 29 秒。

## 先看结论

| 配置 | 是否可对照官方分数 | 6GB 实测 Video 峰值保留 | 59 题 Video smoke 相对原生 |
| --- | --- | ---: | --- |
| FP32 权重 + BF16 autocast（`native`） | 是 | 5,818 MiB | 基准 |
| BF16 权重 | 否，权重发生舍入 | 3,062 MiB | argmax 100%，平均 TV 0.0041 |
| INT8 | 否，实验性量化 | 2,526 MiB | argmax 98.31%，平均 TV 0.0143 |
| NF4 | 否，实验性量化 | 2,270 MiB | argmax 93.22%，平均 TV 0.0479 |

官方原生配置在本机还测得：文本峰值保留 4,364 MiB，2 条 Image smoke 为
4,748 MiB，20 条混合 pilot 为 5,796 MiB。6GB 能跑 0.8B，但 Video 余量很小；
8GB 更稳。4GB 及以下应优先 BF16，仍不足再用 INT8/NF4。2B/4B 的发布权重不属于
≤8GB 的稳妥复现目标。

## 1. 环境

在 PowerShell 中执行：

```powershell
Set-Location .\valen-repro
.\setup.ps1 -Quantization
```

脚本会：

1. 检查源码 commit；
2. 优先复用 `laya-learning/.venv` 的 Python 解释器创建 `Valen/.venv`；
3. 安装 CUDA 12.4 对应的 PyTorch 与仓库精确依赖；
4. 安装可选的 bitsandbytes，并生成 `environment.freeze.txt`；
5. 打印 CUDA、GPU、BF16 与空闲显存预检结果。

中文 Windows 运行测试时保留 UTF-8 模式：

```powershell
$env:PYTHONUTF8 = '1'
$py = (Resolve-Path ..\Valen\.venv\Scripts\python.exe).Path
& $py .\run.py preflight
```

不建议在 Windows 上设置 `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`；
PyTorch 2.6 会明确报告此平台不支持它。

## 2. 下载并校验模型与数据

```powershell
Set-Location .\valen-repro
& $py .\prepare.py
```

若 Hugging Face 匿名限流，先运行 `hf auth login`。下载完成后，脚本会校验完整权重
SHA-256、解包并逐个校验 1,693 个资源，同时生成：

- `smoke-image.jsonl`：2 条 Image；
- `smoke-video.jsonl`：2 条 Video；
- `pilot.jsonl`：10 条 Image + 10 条 Video；
- `eval-image.jsonl`：完整 Image 子集；
- `eval-video.jsonl`：完整 Video 子集。

已有下载可离线复核：

```powershell
& $py .\prepare.py --offline
```

## 3. 推理 smoke

官方原生精度（推荐先跑）：

```powershell
& $py .\run.py infer `
  --model ..\models\Valen-0.8B `
  --dtype native --quant none --execution shared_state `
  --output ..\Valen\output\repro\text-native
```

每次 `--output` 必须是新的或空目录。自定义请求使用：

```powershell
& $py .\run.py infer `
  --model ..\models\Valen-0.8B `
  --request C:\absolute\path\request.json `
  --media-root C:\absolute\path\media `
  --dtype native --quant none --execution shared_state `
  --output ..\Valen\output\repro\my-request
```

## 4. Benchmark 分级执行

先跑官方设置的两个 smoke：

```powershell
& $py .\run.py evaluate --model ..\models\Valen-0.8B `
  --data ..\Valen\data\VisualDecisionBench\smoke-image.jsonl `
  --dtype native --quant none --execution shared_state `
  --output ..\Valen\output\repro\smoke-image-native

& $py .\run.py evaluate --model ..\models\Valen-0.8B `
  --data ..\Valen\data\VisualDecisionBench\smoke-video.jsonl `
  --dtype native --quant none --execution shared_state `
  --output ..\Valen\output\repro\smoke-video-native
```

对输出做强校验，拒绝缺题、重复题、非法概率与指标不一致：

```powershell
& $py .\verify.py `
  --data ..\Valen\data\VisualDecisionBench\smoke-video.jsonl `
  --output ..\Valen\output\repro\smoke-video-native
```

通过后分别跑完整子集。分开运行能把失败重跑范围限制在 Image 或 Video：

```powershell
& $py .\run.py evaluate --model ..\models\Valen-0.8B `
  --data ..\Valen\data\VisualDecisionBench\eval-image.jsonl `
  --dtype native --quant none --execution shared_state `
  --output ..\Valen\output\visualdecisionbench-image-native

& $py .\run.py evaluate --model ..\models\Valen-0.8B `
  --data ..\Valen\data\VisualDecisionBench\eval-video.jsonl `
  --dtype native --quant none --execution shared_state `
  --output ..\Valen\output\visualdecisionbench-video-native

& $py .\verify.py --data ..\Valen\data\VisualDecisionBench\eval-image.jsonl `
  --output ..\Valen\output\visualdecisionbench-image-native
& $py .\verify.py --data ..\Valen\data\VisualDecisionBench\eval-video.jsonl `
  --output ..\Valen\output\visualdecisionbench-video-native
```

验收计数：Image `records=1402, questions=2000`，Video
`records=294, questions=7143`；合计 accuracy 的有效硬标签题数为 8,843。官方模型卡报告
Image accuracy 75.94%、Video accuracy 79.03%。不同 GPU 内核可能让极少数近似并列题翻转，
建议先以完整性校验通过为硬条件，再将子集准确率与官方值按 ±0.2 个百分点排查。

## 5. 显存不足时的降级顺序

先运行 `nvidia-smi`，正常退出浏览器、QQ、游戏覆盖层、录屏和其他模型服务；不要结束
`dwm.exe`、驱动进程或当前 Codex/终端。6GB 跑原生 Video 时应把外部占用压到最低；
模型进程内实测峰值保留约 5.8GB，但 WDDM 的全局“可用显存”与 PyTorch 进程内峰值不是
同一统计口径，不要用两者简单相加判断能否运行。

若仍 OOM，先用 BF16。它通常是 ≤6GB 的最佳实用方案，但不再是官方原生权重精度：

```powershell
& $py .\run.py evaluate --model ..\models\Valen-0.8B `
  --data ..\Valen\data\VisualDecisionBench\eval-video.jsonl `
  --dtype bf16 --quant none --execution shared_state `
  --output ..\Valen\output\visualdecisionbench-video-bf16
```

显存更小时用 INT8；NF4 最省显存，但本机 smoke 的预测漂移明显更大：

```powershell
& $py .\run.py evaluate --model ..\models\Valen-0.8B `
  --data ..\Valen\data\VisualDecisionBench\eval-video.jsonl `
  --dtype bf16 --quant int8 --execution shared_state `
  --output ..\Valen\output\visualdecisionbench-video-int8

& $py .\run.py evaluate --model ..\models\Valen-0.8B `
  --data ..\Valen\data\VisualDecisionBench\eval-video.jsonl `
  --dtype bf16 --quant nf4 --execution shared_state `
  --output ..\Valen\output\visualdecisionbench-video-nf4
```

量化/BF16 输出应与同一输入的原生输出比较：

```powershell
& $py .\verify.py `
  --data ..\Valen\data\VisualDecisionBench\smoke-video.jsonl `
  --output ..\Valen\output\repro\smoke-video-bf16 `
  --compare ..\Valen\output\repro\smoke-video-native
```

只有诊断流程仍 OOM 时才加 `--low-media`。它把视频从 16 帧降到 4 帧并降低像素预算，
会改变任务输入，不能与官方 VisualDecisionBench 分数对比。

## 6. 失败处理

- `CUDA out of memory`：关闭非必要 GPU 应用，换新输出目录重跑；仍失败则按
  native → BF16 → INT8 → NF4 降级。不要把 `--low-media` 结果标成官方复现。
- `Output directory must be new or empty`：保留旧目录作为证据，换一个新目录名；脚本故意
  不覆盖或混合历史结果。
- 下载 401/429：执行 `hf auth login` 后重跑；snapshot 下载会复用已完成缓存。
- `checksum mismatch`：该下载不是锁定 release 或文件损坏；重新下载，不能跳过校验。
- `torchcodec is not installed`：当前锁定环境会回退到 torchvision/av，实测可完成视频评测；
  这是弃用警告，不是本次复现失败。
- bitsandbytes 加载失败：确认使用本目录锁定的 0.49.2；若平台仍不支持，退回 BF16。
- 中途异常：目录中会有 `failure.json`，部分 `predictions.jsonl` 不算成功结果；修复原因后用
  新目录重跑，并再次执行 `verify.py`。

成功目录包含 `predictions.jsonl`、`metrics.json` 和 `run-config.json`。`metrics.json` 额外记录
源码 revision、模型/数据 revision、依赖版本、精度、量化模块、峰值显存与耗时，便于审计。

## 7. 本机验证状态

- 与推理/VisualDecisionBench 直接相关的 16 个上游测试：16/16 通过；
- 上游完整测试集：239 通过、12 跳过、11 失败；失败集中在 Windows 文件锁下未关闭的
  SQLite 临时文件、Windows 上的 DDP/Slurm shell 测试，以及训练 runner 的计时 mock，均不在
  本方案的单卡发布模型推理与评测路径上；
- 原生文本推理、2 条 Image、2 条 Video（16 帧）和 20 条混合 pilot 均已实跑并通过
  `verify.py`；
- BF16、INT8、NF4 均已在 Windows CUDA 环境实跑，并与同一 59 题原生 Video 输出完成漂移
  比较。

因此，本方案对“发布模型的单卡推理与 VisualDecisionBench”已验证；不把当前 Windows 环境
声明为训练、Slurm 或多卡 DDP 的完整支持环境。
