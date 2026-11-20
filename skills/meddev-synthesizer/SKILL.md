---
name: meddev-synthesizer
description: 将医疗器械研究结果合成为可追溯的初筛意见或研究备忘录，去重同源信息、保留冲突与关键资料缺口。
metadata:
  version: "0.3.3"
---

# 医疗器械研究综合兼容入口

先读 [主技能共用边界](../../SKILL.md) 与 [统一证据契约](../../references/evidence-policy.md)，再执行 [综合与验证](../../references/synthesis-validation.md)。

按用户任务使用根目录的产出模板。不能按Agent票数替代证据，不要求灯号或固定优点/风险数量。安装时保留整个仓库结构，本目录不能单独复制使用。

> **发现限制**：本文件位于 `skills/<name>/` 下，只扫描一层的 runtime（如 DeepSeek Harness、Claude Code）**不会**把它列进技能目录。此类环境下请直接调用主技能 `meddev-invest-research`，功能完整、无缺失。本入口供按路径读取的宿主或旧名引用使用。
