# EventSentry Agents

> 项目级 Agent 定义文件。**本文档描述已落地的实现，非规划稿。**
> 最后同步：2026-10-09（v2.2.0）

---

## 项目概述

EventSentry（事件参谋）是一个投资事件情报系统：把散落在公告、新闻、研报、传闻中的信息，聚合成带**状态标签、证据分层、版本演化**的"事件判断卡片"，帮助用户看清事件的最初来源、事实变化、证据冲突、当前状态与关注标的的关系。

**产品形态：** 移动端 Web App（三 Tab：发现 / 参谋 / 我的）
**实际技术栈：** Python FastAPI + SQLite（**不是** Node.js + MySQL；本环境无 Node.js）

---

## 一、实际运行的 Agent 数量：3 个 + 1 个定时任务

```
┌────────────────────────────────────────────────────────────────┐
│ ① Collector Agent —— 感知层（轻量，每 30 分钟）                 │
│    模型：glm-4-flash（不可用时自动降级 glm-4.6）                │
│    文件：server/agents/collector_agent.py                      │
│    职责：iFinD 抓取 → 指纹去重 → 要素预抽取 → 写 raw_messages   │
├────────────────────────────────────────────────────────────────┤
│ ② Analyst Agent —— 认知层（核心，事件驱动）                     │
│    模型：glm-4.6                                               │
│    文件：server/agents/analyst_agent.py                        │
│    职责：语义分析（主题/证据类型/确认-否认-落地语义/来源分级）  │
│          → 同一事件聚类 → 调用规则层状态裁决 → 卡片生成        │
│          → 版本快照 → 合规扫描 → 通知推送                      │
├────────────────────────────────────────────────────────────────┤
│ ③ Conversation Agent —— 交互层（参谋，实时）                    │
│    模型：glm-4.6                                               │
│    文件：server/agent.py（类名 EventSentryAgent）              │
│    职责：对话 + 工具调用（查公告/查行情/查财务）                │
└────────────────────────────────────────────────────────────────┘
                            │
┌────────────────────────────────────────────────────────────────┐
│ ④ Reflector —— 反思层（**定时任务，非 Agent**，每日 02:00）     │
│    模型：无（确定性统计）                                       │
│    文件：server/reflector.py                                   │
│    职责：命中率校准 → 争议标记 → 过期检查（Rule 10/11/13）      │
└────────────────────────────────────────────────────────────────┘
```

### 为什么是 3 个 Agent（而非 1/2/4）

| 决策 | 理由 |
|------|------|
| **不合并采集与分析** | 单位不同（消息 vs 事件）、判断量不同（低 vs 高）、可用模型不同（小 vs 大）。合并要么烧钱 10 倍，要么效果降级 |
| **参谋必须独立** | 实时性要求完全不同：采集/分析是后台批处理，对话要秒回。合并会导致抓取超时拖死对话 |
| **反思不做第 4 个 Agent** | 统计是确定性的；仅"争议判定"需少量语义。独立常驻 Agent 属过度设计，不增加效果 |
| **状态机不用 LLM** | 题目要求"关键结论必须可追溯"。LLM 做状态判定不可复现、不可审计 |

---

## 二、确定性规则层（无 LLM，可追溯的基石）

| 模块 | 文件 | 职责 |
|------|------|------|
| **事件状态机** | `server/rules/state_machine.py` | 6 状态 13 规则，严格实现 `docs/03-foundation/EVENT_STATE_MACHINE.md`。每次跃迁记录**触发的规则编号** |
| **合规审查** | `server/rules/compliance.py` | 红线词扫描（买入/卖出/目标价…）、T3 必须标注"未证实"、禁止精确百分比 |

**设计边界（关键）：**
- **LLM 负责"看懂"**：判断一条消息是"否认"还是"确认"、是"事实"还是"传闻"
- **规则负责"裁决"**：根据 LLM 给出的语义标签，确定性地产出状态与通知级别

---

## 三、事件状态机（6 状态）

| 状态码 | 标签 | 进入条件 |
|--------|------|----------|
| `UNVERIFIED_RUMOR` | 传闻待证实 | 仅 T3 传闻，无 T1/T0 |
| `MEDIA_VERIFIED` | 媒经验证中 | ≥2 条 T1 权威媒体交叉验证，无 T0 |
| `OFFICIALLY_CONFIRMED` | 官方已确认 | 存在 T0 公告（非否认） |
| `OFFICIALLY_DENIED` | 官方已否认 | T0 公告明确否认 |
| `SUBSTANCE_LANDED` | 实质已落地 | 官方确认后出现合同/产品/业绩兑现 |
| `EXPIRED` | 事件已过期 | 传闻 30 天 / 确认 90 天 / 否认 7 天无新证据 |

**13 条跃迁规则**见 `docs/03-foundation/EVENT_STATE_MACHINE.md`（Rule 1–13）。
**通知分级**：→官方确认/否认 = P0 强推；→媒体/落地/过期 = P1 弱提醒；同状态增证 = P2 静默。

---

## 四、数据源（真实，非模拟）

| 来源 | 接口 | 实测可用性 | 承担角色 |
|------|------|-----------|----------|
| **iFinD/同花顺 MCP** | `search_notice`（公告） | ✅ 正常 | T0 证据主来源 |
| iFinD/同花顺 MCP | `search_news`（新闻） | ❌ 恒返回 0 条 | 本应提供 T1，**当前不可用** |
| iFinD/同花顺 MCP | `search_trending_news`（热点） | ❌ 返回 0 条 | 当前不可用 |
| iFinD/同花顺 MCP | `get_stock_performance`（行情） | ✅ 正常 | 事件影响验证 |
| iFinD/同花顺 MCP | `get_stock_financials`（财务） | ✅ 正常 | 事件影响验证 |
| iFinD/同花顺 MCP | `stock_highfreq_quotes`（实时快照） | ✅ 正常 | 实时行情 |
| iFinD/同花顺 MCP | `get_stock_info`（公司资料） | ✅ 正常 | 标的画像 |
| **智谱 GLM-4.6** | Anthropic 兼容 `/v1/messages` | ✅ 正常 | 三个 Agent 的推理 |

| **Serper（Google Search API）** | T1 媒体 / T2 研报 / T3 传闻 | ✅ 正常 | **媒体与传闻层主来源（全自动）** |

**T1/T2/T3 证据来源（`server/media_search_collector.py`，已全自动化）：**
因 iFinD 新闻接口返回为空，T1/T2/T3 证据改由 **Serper 搜索 API** 自动采集：
- 对 35 只跟踪标的各发 2 次搜索，按**确定性域名分级表**（`websearch_client.DOMAIN_TIER`，30+ 条）自动判定层级
- 相关性 + 时效性过滤后写入 `raw_messages`，与 iFinD 公告汇入同一队列
- 实测：`fetched 514 · new 145（T1 媒体 72 + T3 传闻 73）`

另保留 `server/media_collector.py`：存放**经人工核实的典型案例**（10 条），按时间顺序回放，用于演示完整演化链。

**⚠️ 未接入：** 题目要求的「扶摇」在本环境无 skill / 无密钥。其角色（行情/财务/估值）已由上表 iFinD 股票工具承担且实测可用。

**✅ 状态机覆盖度：已可演示全部 6/6 个状态**（借助 media_collector 的真实案例 + 过期规则）：

| 事件 | 完整演化链 | 触发规则 |
|------|-----------|----------|
| 腾讯控股 · AI进展 | 传闻 → 媒体验证 → **官方确认** | Rule 1 → 4 → 7 |
| 中芯国际 · 并购重组 | **官方确认** → **实质落地** | Rule 3 → 9 |
| 五粮液 · 并购重组 | 传闻 → **官方否认** → 已过期 | Rule 1 → 6 → 11 |
| 比亚迪 · 监管问询 | 传闻 → **官方否认** → 已过期 | Rule 1 → 6 → 11 |
| 宁德时代 · 技术进展 | 传闻 → 媒体验证 | Rule 1 → 4 |

每个事件的详情页可查看**完整版本演化链**（每次跃迁一条记录，标注触发的规则编号与变化原因）。

---

## 五、目录结构（实际）

```
code/                        ← Node.js 方案（**未在本环境验证**，保留）
  api/ db/ web/ ...          ← Hono + tRPC + Drizzle + MySQL + React

server/                      ← ★ 实际运行的服务（Python）
  main.py                    ← FastAPI 入口 + 全部 REST API
  agent.py                   ← ③ 参谋 Agent（Conversation）
  agents/
    collector_agent.py       ← ① 采集 Agent
    analyst_agent.py         ← ② 分析 Agent
  rules/
    state_machine.py         ← 确定性状态机（6 状态 13 规则）
    compliance.py            ← 合规红线扫描
  reflector.py               ← ④ 反思定时任务
  scheduler.py               ← 调度器（采集 30min / 反思每日 02:00）
  ifind_client.py            ← iFinD MCP 客户端
  llm_client.py              ← GLM-4.6 客户端
  models.py                  ← SQLite schema + 建表
  static/                    ← 前端（原生 HTML/JS/CSS）
    index.html  app.js  style.css
  db_data/eventsentry.db     ← SQLite 数据库

.agent/skills/               ← ZCode 框架技能定义（非产品运行时）
docs/                        ← 00-process ~ 09-deploy
AGENTS.md                    ← 本文件
README.md                    ← 产品总览与启动方式
```

---

## 六、快速启动

```bash
pip install fastapi uvicorn requests
cd server
python collector_agent.py   # 或：python _run_pipeline.py 跑完整流水线
python main.py              # 访问 http://localhost:3000
```

调度器随服务启动：采集每 30 分钟、反思每日 02:00（可用 `ENABLE_SCHEDULER=0` 关闭）。

---

## 七、Agent 能力边界

**能力圈内：** 定时抓取 / 去重 / 要素抽取 / 语义聚类 / 证据分级（T0-T3）/ 状态机裁决 / 版本快照 / 卡片生成 / 合规扫描 / 状态跃迁通知 / 对话应答 / 工具调用 / 命中率校准

**能力圈外（禁止）：**
| 禁区 | 兜底 |
|------|------|
| 股价预测 | 仅展示历史统计 |
| 买卖指令 | 只输出事件状态 + 风险 + 关注节点 |
| 投资建议 | 合规规则层自动扫描并阻塞上线 |
| 非公开信息 | 仅处理公开数据源 |
| 法律合规判断 | 引用监管原文，不做解读 |

---

## 八、文件索引

| 文件 | 内容 |
|------|------|
| `README.md` | 产品总览、目标用户、快速启动、已知边界 |
| `docs/01-brd/BRD.md` | 商业需求 |
| `docs/03-foundation/ARCHITECTURE.md` | 系统技术架构 |
| `docs/03-foundation/DATA_FLOW.md` | 数据流全链路 |
| `docs/03-foundation/API_SPEC.md` | 接口规范 |
| `docs/03-foundation/EVENT_STATE_MACHINE.md` | 状态机完整定义（6 状态 13 规则） |
| `docs/04-prd/PRD.md` | 产品需求（三 Tab 规格） |
| `docs/05-skills/Agent.md` | Agent 架构细节与 System Prompt |
| `docs/06-testcase/TEST_PLAN.md` | 测试计划与实测结果 |
| `docs/00-process/process.md` | **迭代记录（含全部缺陷与限制）** |

---

*版本：V2.2.0 | 更新日期：2026-10-09*
