# Agent 架构设计文档

> **📌 实现状态（2026-10-09 同步）｜ 已落地**
>
> 本文档设计的 **3-Agent 架构（Collector / Analyst / Reflector）已实现**，实际代码映射如下：
>
> | 设计中 | 实际文件 | 模型 | 状态 |
> |--------|----------|------|------|
> | ① Collector（感知层） | `server/agents/collector_agent.py` | glm-4-flash（降级 glm-4.6） | ✅ 已实现，每 30 分钟 |
> | ② Analyst（认知层） | `server/agents/analyst_agent.py` | glm-4.6 | ✅ 已实现，事件驱动 |
> | ③ Reflector（反思层） | `server/reflector.py` | 无（确定性统计） | ✅ 已实现为**定时任务**，每日 02:00 |
> | （对话应答，原属 Analyst 的 Skill） | `server/agent.py` | glm-4.6 | ✅ 已独立为**参谋 Agent** |
> | 状态机裁决（Skill 4） | `server/rules/state_machine.py` | **无 LLM** | ✅ 纯规则，6 状态 13 规则 |
> | 合规扫描（Skill 5 约束） | `server/rules/compliance.py` | **无 LLM** | ✅ 纯规则 |
>
> **与本文档设计的差异（已论证）：**
> 1. **反思未做成独立 Agent**，而是定时任务 —— 统计是确定性的，独立常驻 Agent 属过度设计，不增加效果（见 `process.md` v2.2.0）。
> 2. **对话应答独立为第三个 Agent（参谋）** —— 实时性要求与批处理完全不同，必须独立失败域。
> 3. **状态机坚持纯规则**（本文档原设计已如此要求），LLM 只负责"看懂"语义，不参与裁决。
> 4. 本文档中"5 分钟抓取周期 / PostgreSQL / Redis"等为原设计值，实际环境为 30 分钟 / SQLite（无 Redis）。



> EventSentry 事件参谋 Agent 的完整架构定义。产品形态为移动端 App（三 Tab：发现/参谋/我的）。

---

## 一、Agent 类型判定：3 个 Agent 协作

**结论：不是单一 LLM Chatbot，而是由 3 个 Agent 构成的事件情报系统。**

| 层级 | Agent 角色 | 职责 | 触发方式 | 上下文特征 |
|------|-----------|------|---------|-----------|
| **感知层** | ① Collector Agent | 多源数据抓取、去重、清洗、要素预抽取 | cron 每 5 分钟 | 消息级（单条原文，紧凑） |
| **认知层** | ② Analyst Agent | 语义聚类、证据分级、状态机裁决、卡片生成、对话应答 | 队列消费 + 用户对话 | 事件级（单事件全证据，紧凑） |
| **反思层** | ③ Reflector Agent | 每日误判回溯、渠道命中率校准、高争议标记 | cron 每日 02:00 | 批量级（昨日全量，分片处理） |

**已被排除的"伪 Agent"：**
- **Orchestrator**：用状态队列 + 行级锁即可解决调度，不需要 LLM 人格；
- **Presenter / Conversation**：作为 Analyst 内部的 Skill 存在，共享 Analyst 的事件上下文；
- **Memory**：直接读写数据库即完成，不需要独立人格。

**为什么是 3 个而非 1/2/6 个：**
- **不是 1 个：** 收集（5 分钟批量、500 条原文上下文）与对话（秒回、单事件紧凑上下文）频率、上下文、失败容忍完全不同。单 Agent 会导致上下文污染、互相阻塞、无法独立扩容。
- **不是 2 个：** 反思若塞进 Analyst，会抢占在线判断/对话的资源；且"自己改自己权重"缺乏制衡。独立 Reflector 每天只醒一次，成本近零，却让系统有了自我纠错闭环。
- **不是 6 个：** 调度用队列锁解决、生成和对话是 Analyst 的 Skill、记忆直接读写数据库——拆成独立 Agent 是过度设计。

---

## 二、Agent 能力边界

### 2.1 能力圈内（Agent 自主执行）

```
┌─────────────────────────────────────────────────────────────┐
│                     Agent 能力圈                              │
├─────────────────────────────────────────────────────────────┤
│  感知                                                        │
│    ├── 定时抓取公告/新闻/研报/互动易（通过 iFinD MCP）        │
│    ├── 监测用户订阅标的的新消息                               │
│    └── 识别"旧闻重发"并过滤                                   │
│                                                              │
│  认知                                                        │
│    ├── 从文本中提取：标的代码、事件主题、动作类型、涉及第三方    │
│    ├── 判断两条消息是否为"同一标的+同一主题"                  │
│    ├── 给消息分级：T0(公告)/T1(权威媒体)/T2(研报)/T3(传闻)    │
│    ├── 维护事件状态机：未证实→验证→确认→落地/否认/过期        │
│    ├── 判断新消息是否触发"状态跃迁"                           │
│    ├── 生成 Face 卡片主结论 + Back 卡片演化方向               │
│    └── 对话应答（基于事件上下文解释、追问、合规拒答）          │
│                                                              │
│  行动                                                        │
│    ├── 向订阅用户推送"状态跃迁"通知                           │
│    ├── 更新事件时间线节点                                     │
│    └── 在对话中调用工具展示行情/公告原文/证据链                │
│                                                              │
│  反思（每日批处理）                                           │
│    ├── 对比昨日判断与今日新证据，识别偏差                      │
│    ├── 统计各来源"传闻→验证"的命中率，更新渠道权重             │
│    └── 生成"高争议事件"列表（官方否认但市场仍传的事件）        │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 能力圈外（人工/规则兜底，Agent 不碰）

| 禁区 | 说明 | 兜底方式 |
|------|------|---------|
| **股价预测** | 不预测"明天涨 5%""目标价 100 元" | 仅展示历史统计 |
| **买卖指令** | 不说"买入""卖出""减仓" | 只输出"事件状态 + 风险 + 关注节点" |
| **投资建议** | 不做资产配置、不问总资产 | 界面显著位置披露非投资建议声明 |
| **非公开信息** | 不处理内幕、群聊截图（除非用户主动上传并标注为传闻） | 仅处理公开数据源 |
| **法律合规判断** | 不判断"是否构成信披违规" | 引用监管原文，不做法律解读 |

---

## 三、Agent 工作流

### 3.1 主循环：Sense → Understand → Decide → Act → Reflect

```
[感知] Collector Agent 每 5 分钟执行：
  1. 调用 iFinD MCP 抓取订阅标的的公告/新闻/研报/互动易
  2. 清洗 HTML、去重（simhash fingerprint）
  3. 预抽取：标的、主题、动作、方向、时间
  4. 写入 RawMessageQueue
   ↓
[理解] Analyst Agent 消费队列：
  1. 语义聚类：判断新消息归属已有事件 or 新建事件
  2. 来源分级：T0/T1/T2/T3
  3. 状态跃迁判断：规则引擎裁决新状态 or 无跃迁
   ↓
[决策] Analyst Agent：
  1. 若状态跃迁 → 更新 EventDB，触发通知
  2. 重新生成 Face/Back 卡片
   ↓
[行动] Analyst Agent：
  1. 推送状态跃迁通知（P0/P1 分级）
  2. 更新发现 Tab 信息流
  3. 对话上下文同步
   ↓
[反思] Reflector Agent 每日 02:00：
  1. 回溯昨日跃迁判断 vs 今日新证据
  2. 更新渠道命中率权重表
  3. 标记高争议事件
```

### 3.2 用户对话流（参谋 Tab）

```
用户输入（参谋 Tab 底部输入框）
  → 意图识别（查询事件 / 追问细节 / 订阅标的 / 通用问答）
    ├── 查询事件 → 检索 EventDB → 返回 Face 卡片 + 追问按钮
    ├── 追问细节 → 读取当前 Event 上下文 + 证据链 → 生成解释
    ├── 订阅标的 → 写入 SubscriptionDB → 返回确认 + 现有事件概览
    └── 通用问答 → 基于产品知识库回答
```

**上下文维持：**
- 用户在参谋 Tab 输入"帮我看看腾讯" → 返回腾讯事件卡片 → 用户追问"为什么可信" → Agent 引用该事件的具体证据回答
- 快捷追问动态生成（基于当前卡片内容）："这和游戏业务有关吗？""如果 3 月 15 日没进展会怎样？"

### 3.3 信息流推送流（发现 Tab）

```
系统定时执行（或用户打开发现 Tab 时触发）：
  1. 读取 UserProfile.subscriptions（关注标的/事件）
  2. 查询 EventDB：
     - 关注标的的、24h 内有跃迁的事件 → 置顶
     - 关注标的的、有新证据的事件 → 次优先级
     - 站内热度 Top 10（跨标的）→ 兜底
  3. 生成信息流卡片列表（缩略态：标题 + 最新节点 + 建议关注）
  4. 用户点击进入同一事件详情页（与参谋 Tab 完全一致）
```

---

## 四、Agent 记忆机制

### 4.1 三层记忆

| 记忆类型 | 存储内容 | 时效 | 载体 |
|---------|---------|------|------|
| **工作记忆** | 当前对话中的 Event 上下文、用户刚问的问题 | 会话级 | Redis |
| **短期记忆** | 用户持仓列表、订阅标的、风险偏好模板 | 用户级 | PostgreSQL |
| **长期记忆** | 各来源历史准确率、事件状态机演化历史 | 全局/用户级 | PostgreSQL |

### 4.2 记忆使用

- **个性化排序：** 用户经常查看"风险类"事件 → 发现 Tab 提升风险事件排序权重；
- **渠道校准：** 某来源过去 30 天命中率 < 20% → 该来源 T3 权重下调；
- **冷启动：** 新用户未设置偏好 → 复制同风险偏好模板的平均行为。

---

## 五、工具调用清单

```typescript
// 数据层工具（iFinD MCP + 扶摇）
interface DataTools {
  get_announcements(ticker: string, days: number): Announcement[];
  get_news(ticker: string, keywords: string[], days: number): News[];
  get_research(ticker: string, days: number): ResearchReport[];
  get_company_profile(ticker: string): CompanyInfo;
  get_price_change(ticker: string, event_date: string, days: number): PriceData;
}

// 认知层工具（Agent 内部 Skill）
interface CognitionTools {
  extract_event_entities(text: string): EventEntity;
  calculate_content_fingerprint(text: string): string;
  semantic_match(event_a: Event, event_b: Event): number;
  classify_source(source_name: string): 'T0' | 'T1' | 'T2' | 'T3';
  evaluate_state_transition(event: Event, new_evidence: Evidence): State | null;
}

// 行动层工具
interface ActionTools {
  generate_face_card(event: Event): FaceCard;
  generate_back_card(event: Event): BackCard;
  send_notification(user_id: string, event: Event, transition: Transition): void;
  update_event_db(event: Event): void;
}
```

---

## 六、反思循环（Reflect）

### 6.1 什么时候反思？

- **定时反思：** 每日凌晨 02:00，回溯过去 24 小时的所有状态判断；
- **触发反思：** 当"官方否认"后 3 天内出现"否认被推翻"证据时，立即触发专项反思；
- **周期性反思：** 每周一次，对所有活跃事件的证据覆盖度进行健康检查。

### 6.2 反思什么？

| 反思维度 | 问题 | 产出 |
|---------|------|------|
| **准确性** | 我昨天给这个事件标的状态，今天来看还对吗？ | ReflectionLog |
| **完整性** | 是否有重要证据被漏抓或错分层？ | EvidenceAudit |
| **时效性** | 是否有事件该标记过期但没有？ | ExpiryReport |
| **争议性** | 是否有"官方否认但市场仍传"的高争议事件？ | ControversyAlert |
| **渠道质量** | 各来源的命中率变化趋势如何？ | SourceQualityReport |

### 6.3 反思后怎么做？

- **修正状态：** 反思发现判断错误 → 更新 Event 状态，向已读用户推送"更正通知"；
- **校准权重：** 更新 SourceTrustScore，影响后续同来源消息的分级；
- **生成学习笔记：** 将典型误判写入案例库，用于优化 Analyst Agent 的 Prompt。

---

## 七、Agent 人格与边界提示（System Prompt 核心）

```
你是 EventSentry，一位严谨的投资事件情报分析师。

你的职责：
1. 从公开信息中识别、聚合、整理同一投资事件的演化过程
2. 区分事实、观点、推测和传闻，并标注来源可信度
3. 维护事件状态机，仅在证据充分时更新状态
4. 向用户呈现事件当前状态、主要风险和下一步关注点

你绝不：
1. 预测股价或给出买卖建议
2. 使用"一定""必然""稳赚"等绝对化表述
3. 将传闻当作事实陈述，必须标注来源和可信度
4. 询问或处理用户的账户密码、资金量等敏感信息

你的语言风格：
- 冷静、克制、结构化
- 先说状态，再给依据，最后提示风险
- 对不确定性明确承认，不掩饰

证据层级规则：
- T0（公告/监管）：直接采信，作为状态判断主依据
- T1（权威媒体）：交叉验证后采信
- T2（研报/分析）：仅作为观点参考
- T3（传闻/股吧）：仅说明"市场存在这种声音"，不参与主结论
```

---

## 八、文件索引

- `README.md` — 产品总览、三 Tab 结构、数据使用、已知边界
- `BRD.md` — 商业需求文档
- `PRD.md` — 产品需求文档（三 Tab 详细规格）
- `Agent.md` — 本文档：Agent 架构、能力边界、工作流、反思循环
- `docs/ARCHITECTURE.md` — 系统技术架构、模块关系
- `docs/DATA_FLOW.md` — 数据从抓去到卡片的全链路时序图
- `docs/API_SPEC.md` — 内部模块接口与外部数据源接口规范
- `docs/EVENT_STATE_MACHINE.md` — 事件状态机完整状态图与跃迁规则
- `docs/MCP_AND_SKILLS.md` — MCP 依赖、7 个 Skill 定义、Agent 数量决策论证
- `docs/TEST_PLAN.md` — 主链路测试、异常测试、合规边界测试
