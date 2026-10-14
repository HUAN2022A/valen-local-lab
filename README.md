# Valen Local Lab

Windows 本地多模态模型实验系统：浏览 VisualDecisionBench 全量案例，并使用 Valen-0.8B 对自定义文本、图片和视频执行结构化推理。

支持案例搜索、筛选、分页、媒体播放、概率分布与原始 JSON 查看；支持 Choice、Noul、Score 自定义问题以及模型显存释放。服务默认只监听 `127.0.0.1:8892`。

## 安装

准备 Windows、Git、[uv](https://docs.astral.sh/uv/) 和支持 CUDA 的 NVIDIA GPU。原始环境为 Windows 11、RTX 3060 Laptop 6GB；默认网页使用 BF16。首次安装和准备数据需要网络，推理在本机执行。

```powershell
git clone https://github.com/HUAN2022A/valen-local-lab.git
Set-Location valen-local-lab
.\install.ps1 -Quantization
$py = Join-Path $PWD 'Valen\.venv\Scripts\python.exe'
& $py .\valen-repro\prepare.py
```

安装脚本下载固定提交的上游源码，创建独立 Python 3.11 环境并安装推理及网页依赖。模型、数据和媒体从锁定的 Hugging Face 版本下载并校验。

## 生成完整案例预测

网页需要两个子集的完整预测；本仓库只包含代码和结果报告，请在本机生成预测文件。每次输出目录必须是新的或空目录。

```powershell
& $py .\valen-repro\run.py evaluate --data .\Valen\data\VisualDecisionBench\eval-image.jsonl --dtype native --quant none --execution shared_state --output .\Valen\output\visualdecisionbench-image-native
& $py .\valen-repro\run.py evaluate --data .\Valen\data\VisualDecisionBench\eval-video.jsonl --dtype native --quant none --execution shared_state --output .\Valen\output\visualdecisionbench-video-native
& $py .\valen-repro\verify.py --data .\Valen\data\VisualDecisionBench\eval-image.jsonl --output .\Valen\output\visualdecisionbench-image-native
& $py .\valen-repro\verify.py --data .\Valen\data\VisualDecisionBench\eval-video.jsonl --output .\Valen\output\visualdecisionbench-video-native
```

原生完整评测在 6GB GPU 上显存余量较小，实测约 58 分钟；详见[复现说明](valen-repro/README.md)的显存配置与限制。网页自定义推理的默认 BF16 配置与原生评测精度不同。

## 启动网页

```powershell
.\valen-repro\case-viewer\start-local.ps1
```

打开 <http://127.0.0.1:8892/>；按 `Ctrl+C` 停止。其他显存配置见[网页说明](valen-repro/case-viewer/README.md)。

## 目录

```text
install.ps1                 环境安装入口
valen-repro/                模型和数据准备、评测、校验及结果报告
  case-viewer/              FastAPI 服务和静态网页
Valen/                      安装时下载的上游源码与本地环境（忽略）
models/                     下载的模型和缓存（忽略）
```

2026-10-13 本机完整复现：9,143 题，其中 8,843 道硬标签题准确率为 78.3784%（6,931 / 8,843）。详见[结果报告](valen-repro/RESULTS.md)。[交接文档](valen-repro/case-viewer/HANDOFF.md)保留原交付时的验证记录，服务状态属于历史快照。

## 上游与发布范围

本项目是 Valen 的本地实验界面和复现工具，并非官方模型项目。上游源码为 [Liuziyu77/Valen](https://github.com/Liuziyu77/Valen)，固定提交 `95f06e8be99bd41e4a98aceddd3e4339c5a8e652`，遵循其 Apache-2.0 许可证。模型与数据分别来自 [Valen-0.8B](https://huggingface.co/Valen-Team/Valen-0.8B) 和 [VisualDecisionBench](https://huggingface.co/datasets/Valen-Team/VisualDecisionBench)，使用时遵循各自条款。

公开仓库不包含模型权重、Benchmark 媒体、预测原始数据、个人上传文件、虚拟环境或历史在线站点配置。
