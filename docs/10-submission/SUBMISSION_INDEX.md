# 提交材料总索引

> EventSentry（事件参谋）—— 投资事件情报与证据时间线
> 版本 v2.6.0 ｜ 2026-10-09

---

## 一、在线资源

| # | 资源 | 地址 |
|---|------|------|
| 1 | **源代码仓库** | https://github.com/RilyWang/EventSentry_Agent |
| 2 | **Web 产品 URL** | https://vegetable-assessment-shower-carey.trycloudflare.com |
| 3 | 线上验证 | 首页/样式/脚本/全部 API 均 HTTP 200，与本地数据一致 |

⚠️ 线上地址为 Cloudflare 无账号快速隧道，**cloudflared 进程停止即失效**。提交前请确认可访问；若失效联系我重开。

---

## 二、提交文档清单

### 必交项

| # | 提交物 | 文件路径 | 内容摘要 |
|---|--------|----------|----------|
| 1 | **README** | `README.md` | 目标用户 · 核心设计 · AI 角色 · 数据使用 · 已知边界 · 未做事项 · 快速启动 |
| 2 | **需求核验报告** | `SUBMISSION.md` | 逐条对照题目要求核验 + 提交清单 + 部署指引 |
| 3 | **AI 使用与验证记录** | `docs/10-submission/AI_USAGE_LOG.md` | AI 角色/提示词策略/防幻觉机制/11 个缺陷记录/能力边界与失败记录 |
| 4 | **测试说明（计划）** | `docs/06-testcase/TEST_PLAN.md` | 主链路 · 数据接口异常 · 合规边界 三类用例 |
| 5 | **测试报告（实测）** | `docs/08-test-reports/TEST_REPORT.md` | 实测 23 项（主链路 9 / 异常 9 / 合规 5）全部通过 + 11 个缺陷 |
| 6 | 演示视频分镜脚本 | `docs/10-submission/DEMO_VIDEO_SCRIPT.md` | 150 秒逐秒分镜 + 旁白（**供你录制视频用**） |

### 设计文档

| # | 文档 | 路径 | 内容 |
|---|------|------|------|
| 7 | 项目 Agent 定义 | `AGENTS.md` | 3 Agent + 1 定时任务、状态机 6 状态、数据源实测表、能力边界 |
| 8 | 商业需求 | `docs/01-brd/BRD.md` | 市场问题、目标用户、商业价值 |
| 9 | 产品需求 | `docs/04-prd/PRD.md` | 三 Tab 规格 + V1→V2.2 实现对照 |
| 10 | 系统架构 | `docs/03-foundation/ARCHITECTURE.md` | 技术栈、模块职责、部署方式 |
| 11 | 数据流全链路 | `docs/03-foundation/DATA_FLOW.md` | 采集→分析→裁决→卡片→通知 全链路时序 |
| 12 | API 规范 | `docs/03-foundation/API_SPEC.md` | 16 个 REST 端点 + iFinD MCP 接口实测 |
| 13 | **事件状态机规范** | `docs/03-foundation/EVENT_STATE_MACHINE.md` | **6 状态 13 规则完整定义 + 跃迁优先级 + 通知映射 + 边界案例** |
| 14 | Agent 架构细节 | `docs/05-skills/Agent.md` | Agent 划分论证、能力圈、记忆机制、System Prompt |
| 15 | MCP 与 Skill 清单 | `docs/05-skills/MCP_AND_SKILLS.md` | MCP 实测可用性表、7 个 Skill 落地情况 |
| 16 | **迭代记录** | `docs/00-process/process.md` | **全部迭代 + 全部缺陷 + 全部限制（含我造成的误删事故）** |
| 17 | 交付计划 | `docs/07-delivery-plans/DELIVERY_PLAN.md` | 里程碑、依赖、风险 |
| 18 | 部署文档 | `docs/09-deploy/DEPLOY.md` | Docker / 云服务器 / Serverless 三路线 |

---

## 三、核心数字（均为实测，可复现）

| 指标 | 数值 |
|------|------|
| 跟踪标的 | 35 只（A股 + 港股各行业龙头） |
| 原始消息 | 352 条（iFinD 公告 + Serper 媒体/传闻 双源） |
| **事件总数** | **140** |
| 证据总数 | **284**（T0 172 · T1 53 · T2 2 · T3 57） |
| 证据类型 | **fact 198 · speculation 60 · rumor 20 · opinion 6** |
| 版本快照 | **173**（update 156 · deny 7 · expire 8 · correct 2） |
| 通知 | **191**（P0 强推 / P1 弱提醒 / P2 静默） |
| **状态覆盖** | **6/6**（官方确认 73 · 未证实传闻 40 · 实质落地 9 · 媒体验证 6 · 官方否认 6 · 已过期 6） |
| Agent 数量 | 3 个（采集 / 分析 / 参谋）+ 1 个反思定时任务 |

**复现命令**：
```bash
cd server
python rules/state_machine.py   # 状态机 13 规则自测
python rules/compliance.py      # 合规规则自测
python _inspect.py              # 数据统计（只读）
python _e2e.py                  # 端到端验证
```

---

## 四、可追溯性（题目硬要求）

| 可追溯对象 | 实现方式 |
|-----------|---------|
| 每条证据的来源 | `evidence_items.source`（来源名）+ `date`（日期）+ `source_url`（原文链接） |
| 证据的可靠性 | `tier` = T0/T1/T2/T3，按来源权威性分级 |
| 每次结论变化的原因 | `event_versions.rule_fired`（触发规则编号）+ `change_reason`（变化原因） |
| 状态跃迁的通知级别 | `event_versions.notification_level` = P0/P1/P2 |
| 数据的四个时间 | `event_time` / `disclosure_time` / `crawl_time` / `updated_at` |

**前端展示**：事件详情页可查看「版本演化链」（每条带规则编号）、「证据权重条」（T0-T3 分层）、「数据来源标注」（抓取/披露/事件时间 + iFinD 标识）。

---

## 五、待完成

| 项 | 负责 |
|----|------|
| 演示视频（60–180 秒） | **需你录制**，脚本见 `DEMO_VIDEO_SCRIPT.md` |
