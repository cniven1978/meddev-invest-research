---
name: meddev-question-refiner
description: 精炼医疗器械研究任务范围。当研究对象、资料或决策问题尚不清楚时，从已有输入提取信息并仅追问关键缺口。
metadata:
  version: "0.3.3"
---

# 医疗器械研究范围精炼

兼容入口。先读 [主技能共用边界](../../SKILL.md) 与 [统一证据契约](../../references/evidence-policy.md)，再执行 [范围精炼](../../references/question-refiner.md)。

只形成当前任务所需研究指令；信息已足够时继续，不强制问卷。安装时保留整个仓库结构，本目录不能单独复制使用。

> **发现限制**：本文件位于 `skills/<name>/` 下，只扫描一层的 runtime（如 DeepSeek Harness、Claude Code）**不会**把它列进技能目录。此类环境下请直接调用主技能 `meddev-invest-research`，功能完整、无缺失。本入口供按路径读取的宿主或旧名引用使用。
