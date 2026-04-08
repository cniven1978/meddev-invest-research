---
name: meddev-invest
description: 医疗器械一级市场股权调研主入口。当用户提到"帮我调研医疗器械项目"、"医疗器械尽调"、"XX赛道分析"时使用此命令。
---

# /meddev-invest

## 使用方法

```
/meddev-invest [项目名称或赛道描述]
```

## 示例

```
/meddev-invest 帮我做心脏瓣膜赛道的投资分析
/meddev-invest 神经介入赛道国内厂商竞争格局分析
/meddev-invest 某创新医疗器械公司做临床阶段尽调
```

## 执行流程

1. **问题精炼** → meddev-question-refiner（先问清楚具体需求）
2. **生成指令** → 输出结构化调研指令
3. **执行调研** → meddev-research-executor（7阶段尽调）
4. **综合报告** → meddev-synthesizer
5. **引文校验** → meddev-citation-validator

## 典型问题精炼

开始调研前，你会收到以下问题：

- 项目属于哪个细分赛道？（高值耗材/IVD/设备/植介入等）
- 目前处于什么发展阶段？（临床中/已拿证/已商业化）
- 最关心哪些维度？（监管壁垒/临床数据/市场/竞争/估值）
- 输出格式偏好？（完整报告/快速概览/清单）

## 与其他工具配合

- **NMPA注册数据** → 自动调用 `nmpa-device-search` 查询注册证信息
- **市场数据** → 自动调用网络搜索抓取行业数据
- **临床试验** → ClinicalTrials.gov 数据库检索
