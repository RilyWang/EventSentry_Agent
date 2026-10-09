---
name: event-analyst
description: 对原始公告/新闻进行主题聚类、证据分级、时间线生成与演化方向推断，输出结构化分析结果。
trigger: analyze, cluster, classify, timeline, 分析, 聚类, 分级, 时间线, 证据链, 演化方向
tags: [nlp, event-analysis, intelligence]
---

# Event Analyst — 事件分析

## 能力范围
- **主题聚类**：将同一标的、同一主题的多条公告聚合为一个事件（如"储能"、"固态电池"、"DeepSeek"）
- **证据分级**：按来源权威性分为 T0/T1/T2/T3
  - T0：公司公告、交易所披露
  - T1：财新/一财/36氪等权威媒体
  - T2：中信证券/中金/国泰君安研报
  - T3：股吧/雪球/微信群聊等传闻
- **时间线节点提取**：按披露时间排序，提取关键状态跃迁节点（传闻出现 → 媒体验证 → 官方确认 → 深化/终止）
- **状态标签判定**：根据最高权重证据决定事件状态（`官方确认` / `媒体验证` / `未证实传闻`）
- **影响方向推断**：判定 `nature`（positive / negative / risk / neutral）
- **演化方向撰写**：基于证据缺口，给出 2-3 个合理演化方向（含概率区间、支撑依据、风险点）
- **传闻识别**：提取并标注无权威来源的市场传闻

## 输入
- `code/data/{ticker}_*.json`（原始公告/新闻/预测）
- 事件主题关键词表（可配置）

## 输出
- 结构化事件对象（尚未封装为最终 EventCard）：
  ```typescript
  {
    ticker, ticker_name, theme, headline,
    status, nature, nature_label,
    timeline: TimelineNode[],
    evidence: { T0: EvidenceItem[], T1: ..., T2: ..., T3: ... },
    directions: Direction[],
    rumors: Rumor[],
    updated_at
  }
  ```

## 规则引用
- 时间折叠：跨度 > 1 年的旧节点自动折叠
- 旧闻重发：fingerprint 去重，不重复计算
- 不预测股价涨跌，只描述事件本身走向

## 关联文档
- `docs/03-foundation/DATA_FLOW.md` §2.2、§Node 2/3
- `docs/04-prd/PRD.md` §2.3、§2.4
- `docs/03-foundation/EVENT_STATE_MACHINE.md`

## 触发时机
用户提及"分析事件"、"聚类"、"生成时间线"、"证据分级"、"推演后续"时自动触发。
