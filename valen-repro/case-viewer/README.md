# Valen Local Lab

本地可视化浏览器，读取已经完成的 VisualDecisionBench 复现结果，并在同一页面调用
Valen-0.8B 做自定义文本、图片或视频推理。页面和接口只监听 `127.0.0.1`，不会上传测试
数据或用户媒体。

## 启动

先按仓库根目录 README 完成安装、数据下载和完整预测。以下命令从仓库根目录执行。

```powershell
Set-Location .\valen-repro\case-viewer
.\start-local.ps1
```

打开 <http://127.0.0.1:8892/>。按 `Ctrl+C` 停止服务。

默认使用 BF16 权重和完整 16 帧视频配置，适合本机 6GB GPU：

```powershell
.\start-local.ps1 -Precision bf16 -Quantization none
```

其他可选配置：

```powershell
# 官方原生权重精度；视频显存余量较小
.\start-local.ps1 -Precision native -Quantization none

# 更低显存，但属于实验性量化
.\start-local.ps1 -Precision bf16 -Quantization int8
.\start-local.ps1 -Precision bf16 -Quantization nf4

# 最后兜底：视频降为 4 帧，会改变输入，不能作为官方复现分数
.\start-local.ps1 -Precision bf16 -LowMedia
```

## 功能

- 导入 Image 2,000 题和 Video 7,143 题，共 9,143 题；
- 按图片/视频、Choice/Noul/Score、正确/错误/软标签筛选；
- 搜索题目、来源、ID、候选答案或输出键；
- 展示媒体、完整问题、概率分布、模型预测、标准答案和原始 JSON；
- 自定义文本、图片或视频输入；模型按需加载并常驻显存；
- 页面内可卸载模型，立即释放 PyTorch 占用的显存缓存。

服务端复用 `<workspace>\Valen\.venv` 的 uv 环境，数据、媒体、模型和预测
结果均直接读取当前工作区，不复制整套 Benchmark。
