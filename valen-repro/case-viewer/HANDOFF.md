> 公开仓库整理于 2026-10-14。以下为原本机交接记录；服务状态和 Git 状态是交付时的历史快照。<workspace> 表示本仓库根目录。安装和公开发布范围以根目录 README 为准。旧站点配置与示例媒体未纳入本仓库。

# Valen Local Lab 交接文档

交接日期：2026-10-14
项目目录：`<workspace>\valen-repro\case-viewer`

## 1. 当前结论

本地可视化与自定义推理功能已经完成，可以直接交付使用。

- 本地地址：<http://127.0.0.1:8892/>
- 当前服务状态：运行中
- 当前模型状态：已加载并可推理
- 当前配置：Valen-0.8B、BF16、无量化、`cuda:0`
- 数据范围：VisualDecisionBench 全量 9,143 题、1,696 条媒体记录
- 复现硬标签准确率：78.38%（6,931 / 8,843）
- 页面仅监听 `127.0.0.1`，数据和上传媒体不会发送到外部服务

当前版本是本地交付版本，不需要继续在线发布。

## 2. 已完成功能

### 完整案例

- 导入 Image 2,000 题和 Video 7,143 题；
- 按图片、视频筛选；
- 按 Choice、Noul、Score 筛选；
- 按预测正确、预测错误、软标签筛选；
- 搜索题目、来源、记录 ID、候选答案和输出键；
- 分页查看全部 9,143 题；
- 展示输入媒体、完整问题、选项、模型概率、预测答案和标准答案；
- 展开查看原始输入与输出 JSON；
- 视频支持浏览器分段加载和拖动播放。

### 自定义推理

- 支持纯文本输入；
- 支持上传图片；
- 支持上传视频；
- 支持 Choice、Noul、Score 三种结构化输出；
- 模型首次使用时按需加载，随后常驻显存；
- 展示答案、概率、置信度、推理耗时和完整 JSON；
- 页面内可以卸载模型并释放 PyTorch 显存；
- 已增加“填入示例”按钮，自动填写背景文字、问题和候选项，可直接运行。

示例内容为：

```text
State: A cat is sitting on a blue sofa near the window.
Question: Which animal is sitting on the sofa?

cat | A cat
dog | A dog
rabbit | A rabbit
bird | A bird
```

## 3. 启动与停止

### 正常启动

```powershell
Set-Location .\valen-repro\case-viewer
.\start-local.ps1
```

打开：<http://127.0.0.1:8892/>

默认启动参数：

```text
Precision     bf16
Quantization  none
Device        cuda:0
Port          8892
LowMedia      false
```

停止服务：在启动服务的 PowerShell 窗口按 `Ctrl+C`。

### 其他显存配置

官方原生权重精度，视频显存余量较小：

```powershell
.\start-local.ps1 -Precision native -Quantization none
```

实验性量化：

```powershell
.\start-local.ps1 -Precision bf16 -Quantization int8
.\start-local.ps1 -Precision bf16 -Quantization nf4
```

最后兜底的低媒体模式：

```powershell
.\start-local.ps1 -Precision bf16 -LowMedia
```

`-LowMedia` 会把视频降为 4 帧并降低像素预算，因此不能将该结果标记为官方设置复现结果。

## 4. 目录与文件职责

```text
case-viewer/
├─ server.py                 FastAPI 服务、Benchmark 索引、媒体接口和模型管理
├─ start-local.ps1           本地启动入口
├─ requirements-local.txt    本地网页新增依赖
├─ README.md                 用户使用说明
├─ HANDOFF.md                本交接文档
├─ dist/
│  ├─ index.html             页面结构
│  ├─ styles.css             页面样式与响应式布局
│  ├─ app.js                 筛选、分页、案例详情和推理交互
│  └─ assets/                早期四案例静态资源，当前全量浏览不依赖它们
└─ .local-runtime/           临时上传目录，已加入 .gitignore
```

数据、媒体和模型不复制到网页目录，服务直接读取：

```text
<workspace>\Valen\data\VisualDecisionBench
<workspace>\Valen\output\visualdecisionbench-image-native
<workspace>\Valen\output\visualdecisionbench-video-native
<workspace>\models\Valen-0.8B
```

Python 环境复用：

```text
<workspace>\Valen\.venv\Scripts\python.exe
```

网页额外依赖已经通过 uv 安装进该环境：

```text
fastapi==0.115.12
uvicorn[standard]==0.34.0
python-multipart==0.0.20
```

## 5. 数据与模型版本

| 项目 | 固定版本 |
| --- | --- |
| Valen 源码 | `95f06e8be99bd41e4a98aceddd3e4339c5a8e652` |
| Valen-0.8B | `c2c481fcb319bd9ae834abc7c6373271710cf24e` |
| VisualDecisionBench | `0c9e97031ca1dbc3e4f87640c03fc6c56dc8d685` |
| 模型权重 SHA-256 | `465714dd28702c4232d9233c2a2157d366967c541b2a27d9dadccc816304fd48` |

完整复现结果：

| 子集 | 题数 | Accuracy |
| --- | ---: | ---: |
| Image | 2,000 | 75.7647% |
| Video | 7,143 | 79.0004% |
| 合计硬标签 | 8,843 | 78.3784% |

完整评测耗时约 58 分 29 秒。更详细结果见：

```text
<workspace>\valen-repro\RESULTS.md
<workspace>\valen-repro\README.md
```

## 6. 服务接口

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/summary` | Benchmark 汇总与模型状态 |
| GET | `/api/cases` | 分页、搜索和筛选案例 |
| GET | `/api/cases/{case_id}` | 单题完整详情 |
| GET | `/api/media/{asset_path}` | 读取本地图片或视频，支持 Range |
| GET | `/api/model/status` | 模型、显存和运行状态 |
| POST | `/api/model/unload` | 卸载模型并释放显存 |
| POST | `/api/infer` | 自定义文本、图片或视频推理 |

`/api/infer` 使用 `multipart/form-data`：

```text
state_text      可选背景文字
instructions    必填问题
question_type   choice / noul / score
criteria        Choice 或 Score 标准，每行一条
media_file      可选图片或视频
```

Choice 选项推荐格式：

```text
A | 第一个选项
B | 第二个选项
```

## 7. 已完成验证

### 数据与接口

- `/api/summary` 返回 9,143 题和 1,696 条记录；
- Image 计数 2,000，Video 计数 7,143；
- 硬标签 8,843 题，正确 6,931 题；
- 视频错误 Noul 筛选返回 109 条；
- 搜索 `Dave Rutledge` 能定位到唯一案例；
- 视频 Range 请求返回 HTTP 206。

### 自定义推理

已实跑三类输入：

| 输入 | 结果 | 推理耗时 |
| --- | --- | ---: |
| 文本 | `cat`，置信度约 99.95% | 3.87 秒 |
| 图片 | `image`，置信度约 99.96% | 0.96 秒 |
| 视频 | `video`，置信度约 66.96% | 2.82 秒 |

上述时间来自本机 RTX 3060 Laptop GPU，仅作为当前环境参考。

### 页面

- 桌面与窄窗口响应式布局已检查；
- 完整案例筛选、分页和详情切换已检查；
- 自定义表单提交与结果渲染已检查；
- “填入示例”按钮已检查，能够正确填充全部字段；
- 图片显示和视频播放已检查。

## 8. 当前 Git 状态

`case-viewer` 目录之前为历史在线快照初始化过独立 Git 仓库，当前 HEAD：

```text
0b9b055d6d8d098313333deb1cfad6d1bb4acd42
```

本地版代码目前没有提交，属于工作区改动。不要执行 `git reset --hard`、`git checkout -- .`
或其他会覆盖工作区的操作，否则会丢失本地版本。

当前应保留的改动包括：

```text
M  .gitignore
M  dist/index.html
?? README.md
?? HANDOFF.md
?? dist/app.js
?? dist/styles.css
?? requirements-local.txt
?? server.py
?? start-local.ps1
```

如需提交，先确认是否仍需要保留历史在线仓库关系，再创建一个新的本地功能提交，不要覆盖
远端历史。

## 9. 在线版本边界

早期曾创建过一个私有在线静态快照：

```text
https://valen-test-cases.whitebrook128.chatgpt.site
```

用户随后明确要求改为本地运行。该在线地址不是当前交付版本，也没有自定义本地模型推理能力。
后续不要自动发布或同步当前代码；除非用户再次明确要求，否则只维护本地版本。

## 10. 已知限制

1. 页面只能在本地服务运行时访问，直接双击 `index.html` 无法读取 API。
2. 模型是单实例并串行推理，同时提交多个请求会排队。
3. 自定义上传文件在推理结束后删除，不保存历史记录。
4. BF16 是当前 6GB GPU 的实用默认配置，但不等同于官方原生权重精度。
5. Native 视频推理的显存余量很小，运行前应关闭不必要的 GPU 应用。
6. INT8 和 NF4 是实验性量化，会产生一定预测漂移。
7. 当前没有用户账户、持久化任务队列或推理历史数据库。
8. `.openai/hosting.json` 来自历史在线快照，本地服务不依赖它。

## 11. 常见故障

### 端口被占用

```powershell
.\start-local.ps1 -Port 8893
```

然后访问 <http://127.0.0.1:8893/>。

### CUDA out of memory

处理顺序：

1. 在页面点击“释放显存”；
2. 关闭其他 GPU 应用；
3. 重启并使用 BF16；
4. 仍不足时改用 INT8 或 NF4；
5. 最后才使用 `-LowMedia`。

不要结束 `dwm.exe`、显卡驱动进程或当前 Codex 进程。

### 依赖缺失

```powershell
& uv pip install `
  --python <workspace>\Valen\.venv\Scripts\python.exe `
  -r <workspace>\valen-repro\case-viewer\requirements-local.txt
```

### 页面能打开但没有数据

检查以下文件是否存在：

```text
Valen\data\VisualDecisionBench\eval-image.jsonl
Valen\data\VisualDecisionBench\eval-video.jsonl
Valen\output\visualdecisionbench-image-native\predictions.jsonl
Valen\output\visualdecisionbench-video-native\predictions.jsonl
```

## 12. 建议的后续工作

按优先级建议：

1. 将当前本地版整理为一次明确的 Git 提交，避免工作区被误清理；
2. 增加自定义推理历史记录与导出 JSON；
3. 增加“从当前 Benchmark 案例复制到自定义推理”；
4. 增加按数据源和置信度范围筛选；
5. 增加批量自定义推理与任务进度显示；
6. 如确实需要局域网访问，再单独设计访问控制，不要直接将 `0.0.0.0` 暴露出去。

## 13. 交接检查清单

- [ ] 确认 `Valen\.venv` 存在；
- [ ] 确认模型和完整 Benchmark 数据存在；
- [ ] 运行 `start-local.ps1`；
- [ ] 打开 `/api/summary`，核对问题数为 9,143；
- [ ] 打开网页，测试图片和视频案例；
- [ ] 点击“填入示例”，运行一次自定义推理；
- [ ] 确认页面可卸载模型并释放显存；
- [ ] 不要误发布到历史在线站点；
- [ ] 不要清理当前未提交工作区。
