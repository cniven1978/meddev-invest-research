---
name: meddev-research-executor
description: 执行医疗器械监管、临床、准入商业化、竞争、财务和治理研究。按当前资料与研究问题加载有关维度，不默认启动并行Agent。
metadata:
  version: "0.3.4"
---

# 医疗器械研究执行兼容入口

读取并执行 [主技能](../../SKILL.md)。主技能名 meddev-invest-research 保留在仓库根目录；本入口名称与所在目录一致。

根据任务加载主技能列出的领域参考，原六维研究＋第七阶段综合的能力保留。只有实际执行、有证据的事项才能标为完成尽调。工具及并行能力以宿主环境为准；不得因本入口存在而声称检索或多Agent执行已实现。

安装时保留整个仓库结构，本目录不能单独复制使用。

> **发现限制**：本文件位于 `skills/<name>/` 下，只扫描一层的 runtime（如 DeepSeek Harness、Claude Code）**不会**把它列进技能目录。此类环境下请直接调用主技能 `meddev-invest-research`，功能完整、无缺失。本入口供按路径读取的宿主或旧名引用使用。
