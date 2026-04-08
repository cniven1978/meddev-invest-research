# meddev-invest-research

> 医疗器械一级市场股权调研 Skill Pack for OpenClaw

## 简介

专门用于医疗器械一级市场（被投项目）投资尽调的完整 Skill 套件，参考 `liangdabiao/Claude-Code-Stock-Deep-Research-Agent` 框架，针对医疗器械行业定制开发。

## 包含组件

| Skill | 职责 |
|-------|------|
| `meddev-question-refiner` | 调研问题精炼（先问清楚再动手） |
| `meddev-research-executor` | 7阶段尽调执行引擎（核心） |
| `meddev-synthesizer` | 多Agent结果综合 |
| `meddev-citation-validator` | 引文质量校验 |

## 使用命令

```
/meddev-invest [项目名称或赛道描述]
```

## 7阶段尽调框架

```
Phase 1 → 监管格局与注册证分析（NMPA/FDA/CE注册壁垒）
Phase 2 → 临床证据与循证医学（临床试验数据与证据等级）
Phase 3 → 市场准入与商业化（医保/集采/定价/渠道）
Phase 4 → 竞争格局与技术壁垒（直接竞品/护城河/SWOT）
Phase 5 → 财务质量与估值（收入/现金流/可比估值）
Phase 6 → 团队评估与治理（创始人背景/股权结构/治理）
Phase 7 → 综合报告与投资信号（信号灯/退出路径）
```

## 数据来源标准（A-E级）

| 等级 | 来源类型 | 可信度 |
|------|---------|--------|
| A级 | NMPA官网、ClinicalTrials.gov | 最高可信 |
| B级 | 招股书、上市公司年报 | 较高可信 |
| C级 | 权威行业研究报告 | 中等可信 |
| D级 | 媒体报道（需标注） | 参考用 |
| E级 | 传言/无来源 | 不用 |

## 配合使用

- **nmpa-device-search**：自动查询NMPA注册证数据
- **pdf-text-extractor**：解析BP PDF文档
- **ClinicalTrials.gov**：查询临床试验数据

## 安装

放入 OpenClaw skills 目录：
```bash
cp -r meddev-invest-research ~/.openclaw/skills/
```

## 使用示例

```
/meddev-invest 帮我做心脏瓣膜赛道的投资分析
/meddev-invest 神经介入赛道国内厂商竞争格局
/meddev-invest XX公司医疗器械产品尽调
```

## 免责声明

本工具输出的内容仅供投资研究参考，不构成任何投资建议。数据来源于公开信息，准确性以原始来源为准。
