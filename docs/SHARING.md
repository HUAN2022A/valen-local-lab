# 社区分享素材

以下内容为草稿，尚未发布到外部社区。分享前确认渠道允许项目展示；上游维护者是否收录链接由对方决定。

## 中文介绍

在 Windows、6GB 显存上跑通 Valen-0.8B 后，我把案例浏览和本地推理整理成了 Valen Local Lab。

它可以搜索和筛选多模态评测题，查看输入媒体、预测概率、标准答案与 JSON，也可以上传图片或视频，运行 Choice、Noul、Score 自定义问题。

本机完整复现覆盖 9,143 题；其中 8,843 道硬标签题准确率为 78.3784%。原生完整评测约 58 分钟，网页推理默认 BF16，两者精度配置不同。

仓库还提供无需显卡和模型下载的界面体验模式。里面的 4 道题和概率均为人工合成，只用于展示交互。

代码、安装说明和结果报告：https://github.com/HUAN2022A/valen-local-lab

欢迎反馈安装问题，或分享其他 GPU 的运行情况。

## English introduction

I built Valen Local Lab after reproducing Valen-0.8B on Windows with an RTX 3060 Laptop 6GB GPU.

The interface lets you filter multimodal benchmark cases, inspect media and probabilities, compare predictions with reference answers, and run custom local text/image/video inference.

The full local run covered 9,143 questions, reaching 78.3784% accuracy on 8,843 hard-label questions. Native evaluation took about 58 minutes on this machine. The custom inference interface defaults to BF16, a different precision profile.

A no-GPU interface demo is included, using four explicitly labeled synthetic examples. It requires no model or benchmark downloads and does not run inference.

Code, setup and measured results: https://github.com/HUAN2022A/valen-local-lab

Feedback on installation and other GPU configurations is welcome.

## 推广顺序

1. 在上游允许的 Discussions 或相关模型社区分享上述实测结果与工具；不要创建与缺陷无关的宣传 Issue。
2. 将截图、运行配置和典型错误案例整理成知乎文章或 B 站演示。
3. 后续有具体改进或新硬件结果时再分享更新。

截图：`media/demo.png`、`media/error-case.png`。分享预览图：`media/social-preview.png`。
