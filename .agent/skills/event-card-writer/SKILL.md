---
name: event-card-writer
description: 将事件分析结果封装为前端可直接消费的 EventCard 结构化数据，写入 events.ts / events.json。
trigger: card, write, generate, event-card, 写卡片, 生成卡片, 事件卡片, 结构化输出
tags: [code-generation, frontend-data, event-card]
---

# Event Card Writer — 事件卡片生成

## 能力范围
- 将 `event-analyst` 输出的结构化事件封装为符合前端类型的 `EventCard` 对象
- 生成 `code/src/data/events.ts`（TypeScript 模块，含类型注解 + 查询函数）
- 生成 `code/src/data/events.json`（纯 JSON 备份）
- 确保 headline、timeline、evidence、directions、rumors 格式符合前端组件预期

## 输入
- `event-analyst` 输出的结构化事件对象
- `code/src/types/index.ts` 中的类型定义

## 输出
- `code/src/data/events.ts`：
  ```typescript
  export const events: EventCard[] = [...]
  export const getEvents = () => events
  export const searchEvents = (query: string) => {...}
  export const getEventById = (id: string) => {...}
  ```
- `code/src/data/events.json`：同数据的 JSON 备份

## 规范约束
- `headline` 格式：`{ticker_name} · {核心动作}`，如"腾讯控股 · 微信接入DeepSeek"
- `nature_label`：利好 / 利空 / 中性 / 风险 / 待验证
- `timeline` 节点必须包含：`date`、`status_label`、`source_tier`、`summary`、`is_current`
- `directions` 每条必须包含：`scenario`、`probability`、`supporting`、`risk`
- `rumors` 必须标注来源和可信度，且与 `directions` 视觉区隔
- `updated_at` 使用最后状态跃迁时间

## 关联文档
- `docs/03-foundation/DATA_FLOW.md` §2.3、§Node 4/5
- `docs/04-prd/PRD.md` §2.3（卡片结构）
- `code/src/types/index.ts`

## 触发时机
用户提及"生成卡片"、"写 events.ts"、"封装事件数据"、"更新静态数据"时自动触发。
