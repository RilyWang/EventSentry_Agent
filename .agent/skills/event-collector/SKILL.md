---
name: event-collector
description: 从 iFinD 等金融数据源采集原始公告、新闻、研报与预测数据，输出标准化原始文件。
trigger: collect, fetch, crawl, ingest, 采集, 抓取, 爬取, 数据获取, 公告, 新闻
tags: [data-ingestion, ifind, pipeline]
---

# Event Collector — 事件采集

## 能力范围
- 调用 `ifind-finance-data` skill 获取指定标的的公告、新闻、预测数据
- 批量并行请求多只股票，输出标准化的原始 JSON 文件
- 管理采集频率与去重逻辑（fingerprint 去重，不重复计算）

## 输入
- 目标标的列表，如 `["300750.SZ", "002594.SZ", "688981.SH"]`
- 时间范围，如 `"2025-09-01"` ~ `"2025-10-08"`
- 数据类型：`announcement` | `news` | `forecast` | `info`

## 输出
- `code/data/{ticker}_announcements.json`
- `code/data/{ticker}_info.json`
- `code/data/{ticker}_forecast.json`
- 标准字段：`reportDate`, `reportTitle`, `reportType`, `content` 等

## 工作流
```
定义标的列表 → 并行请求 iFinD MCP → 解析 CSV/JSON →
去重（fingerprint） → 按标的写入原始 JSON → 生成采集报告
```

## 关联文档
- `docs/03-foundation/DATA_FLOW.md` §2.1
- `docs/04-prd/PRD.md` §3.2

## 触发时机
用户提及"抓数据"、"更新公告"、"采集新闻"、"拉取 iFinD 数据"时自动触发。
