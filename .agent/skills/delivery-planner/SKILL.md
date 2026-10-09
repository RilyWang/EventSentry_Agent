---
name: delivery-planner
description: 围绕 EventSentry 事件参谋的迭代路线，制定从 V1 静态版到 V2 后端化的里程碑与交付计划。
trigger: delivery, plan, milestone, roadmap, 交付, 排期, 里程碑, 路线, 迭代计划
tags: [project-management, planning, roadmap]
---

# Delivery Planner — 交付计划

## 能力范围
- 根据 PRD 和架构文档拆解 EventSentry 的交付里程碑
- 输出 V1 → V2 的迁移路线图（静态托管 → 后端化 → 实时数据 → LLM Agent）
- 评估数据pipeline、前端组件、合规审查等模块的依赖关系与并行度

## EventSentry 标准交付阶段

| 阶段 | 目标 | 关键产出 |
|------|------|----------|
| **P0 数据层** | 建立 iFinD → 原始 JSON → 结构化事件的构建期流水线 | `events.ts` + `events.json` |
| **P1 卡片层** | 完成 EventCard 组件（Face + Back + 详情页） | `EventCardItem.tsx` + `EventDetail.tsx` |
| **P2 三 Tab** | 完成发现/参谋/我的三个主页面 | `DiscoverPage` + `AdvisorPage` + `ProfilePage` |
| **P3 合规层** | 建立合规审查流水线，阻塞红线内容上线 | `compliance-guard` 审查报告 |
| **P4 部署** | 静态构建 + GitHub Pages 部署 | `dist/` + 线上可访问 |
| **V2 后端化** | Hono + tRPC + PostgreSQL，Collector/Analyst/Reflector Agent | 实时数据 + 跨设备同步 |

## 依赖关系
```
P0 数据层 ──▶ P1 卡片层 ──▶ P2 三 Tab ──▶ P3 合规层 ──▶ P4 部署
  │              │              │
  └──────────────┴──────────────┘
        可并行：合规规则制定、UI 设计、测试用例编写
```

## 输出格式
1. 里程碑列表（编号、目标、验收标准、截止日期）
2. 甘特图（Mermaid）
3. 风险与缓冲（如 iFinD 接口变更、合规审核周期）

## 关联文档
- `docs/04-prd/PRD.md` §六（开放问题）
- `docs/03-foundation/ARCHITECTURE.md` §七（V2 扩展路线）
- `docs/07-delivery-plans/`

## 触发时机
用户提及"排期"、"里程碑"、"V2计划"、"什么时候上线"、"迭代路线"时自动触发。
