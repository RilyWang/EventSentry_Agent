# 数据流文档

> **📌 实现状态（2026-10-09 同步）**
> 本文档描述 **V1 纯静态构建期数据流**，属于历史设计。
> **当前实际数据流（V2.2.0）**：
> ```
> 调度器(30min) → 采集 Agent → iFinD MCP(search_notice)
>   → 指纹去重 → 要素预抽取 → raw_messages 队列
>       ↓
> 分析 Agent → GLM-4.6 语义分析(主题/证据类型/确认-否认-落地/来源分级)
>   → GLM-4.6 聚类(归属已有事件 or 新建) → 规则层状态裁决(状态机)
>   → 卡片生成(GLM-4.6) → 合规扫描(规则) → event_versions 快照 → notifications
>       ↓
> 参谋 Agent → 对话 + 工具调用(iFinD 公告/行情/财务) → 带引用的回答
>       ↓
> 反思任务(每日 02:00) → 命中率校准 → 争议标记 → 过期检查(Rule 10/11/13)
> ```
> 代码位置：`server/agents/`、`server/rules/`、`server/reflector.py`、`server/scheduler.py`。

> 版本：V1.0（MVP）｜ 更新日期：2025-10-08
> 
> **说明：** V1 为纯前端静态应用，数据流分为"构建期数据获取"和"运行时前端渲染"两个阶段。本文档描述 V1 实际数据流。

---

## 一、全链路数据流概览

```
┌─────────────────────────────────────────────────────────────────────┐
│                        构建期（Build Time）                          │
│                                                                      │
│   iFinD MCP  ──▶  Python 脚本  ──▶  结构化事件  ──▶  静态 TS 模块   │
│   原始公告          清洗/聚类          时间线/证据        打包进产物   │
│                                                                      │
│   频率：每次构建前手动/脚本触发                                        │
│   输出：src/data/events.ts + src/data/events.json                    │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                              npm run build
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        运行时（Runtime）                             │
│                                                                      │
│   用户打开网页                                                      │
│       │                                                             │
│       ├── 发现 Tab：import events.ts → 内存过滤/排序 → 渲染卡片       │
│       │                                                             │
│       ├── 参谋 Tab：输入关键词 → searchEvents() → 渲染卡片           │
│       │                                                             │
│       └── 我的 Tab：localStorage.getItem('eventsentry_user')         │
│                    → 解析 User 对象 → 渲染持仓/关注/偏好             │
│                                                                      │
│   用户操作（关注/添加持仓/修改偏好）                                   │
│       │                                                             │
│       └── localStorage.setItem('eventsentry_user', updatedUser)      │
│           → 即时持久化，页面刷新不丢失                                │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 二、构建期数据流（构建前执行）

### 2.1 iFinD 数据获取

```
Python 脚本执行
   │
   ├── 目标标的定义
   │      stocks = [
   │        ("300750.SZ", "宁德时代"),
   │        ("002594.SZ", "比亚迪"),
   │        ("688981.SH", "中芯国际"),
   │        ("000858.SZ", "五粮液"),
   │        ("00700.HK", "腾讯控股"),
   │      ]
   │
   ├── 对每个标的并行请求
   │      ├─ ifind_get_stock_announcement(ticker, "2025-09-01", "2025-10-08")
   │      ├─ ifind_get_stock_info(ticker)
   │      └─ ifind_get_forecast(ticker, "2025-01-01", "2025-10-08")
   │
   ├── 解析 CSV 响应
   │      csv.DictReader → List[Dict]
   │      字段：reportDate, reportTitle, ...
   │
   └── 保存原始数据
          /data/{ticker}_announcements.json
          /data/{ticker}_info.json
          /data/{ticker}_forecast.json
```

### 2.2 数据结构化（人工 + 规则）

```
原始公告数据
   │
   ├── 主题聚类（规则匹配关键词）
   │      "储能" → 储能业务扩张事件
   │      "固态电池" → 固态电池研发事件
   │      "仰望" → 高端车型销量事件
   │      "扩产" / "产线" → 先进制程扩产事件
   │      "中秋" / "国庆" / "动销" → 双节动销事件
   │      "AI" / "DeepSeek" / "大模型" → 微信AI功能事件
   │
   ├── 时间线节点生成
   │      按公告时间排序 → 提取关键状态节点
   │      节点标签：传闻出现 → 媒体验证 → 官方确认
   │
   ├── 证据分级（规则表）
   │      公司公告 → T0
   │      财新/第一财经/36氪 → T1
   │      中信证券/中金/国泰君安研报 → T2
   │      股吧/雪球/微信群聊 → T3
   │
   ├── 演化方向撰写（基于证据缺口）
   │      方向A：乐观情景 + 支撑依据 + 风险点
   │      方向B：谨慎情景 + 支撑依据 + 风险点
   │
   └── 输出结构化事件
          EventCard {
            id, ticker, ticker_name, theme, headline,
            status, nature, nature_label,
            timeline: TimelineNode[],
            evidence: {T0, T1, T2, T3},
            directions: Direction[],
            rumors: Rumor[],
            updated_at
          }
```

### 2.3 静态数据打包

```
结构化事件数组（6 个事件）
   │
   ├── 写入 src/data/events.ts
   │      // TypeScript 模块，包含类型注解和查询函数
   │      export const events: EventCard[] = [...]
   │      export const getEvents = () => events
   │      export const searchEvents = (query) => {...}
   │
   ├── 写入 src/data/events.json（备份）
   │      // 纯 JSON，供外部工具读取
   │
   └── Vite 构建时打包
          import { getEvents } from '@/data/events.ts'
          → Tree Shaking → 仅保留使用到的代码
          → 打包进 dist/assets/index-{hash}.js
```

---

## 三、运行时数据流（浏览器端）

### 3.1 发现 Tab 数据流

```
用户打开"发现"Tab
   │
   ├── 组件挂载：DiscoverPage.tsx
   │      import { getEvents } from '@/data/events.ts'
   │      const allEvents = getEvents()  // 内存读取，O(1)
   │
   ├── 渲染事件列表
   │      allEvents.sort((a, b) => b.updated_at.localeCompare(a.updated_at))
   │      → 按时间倒序排列
   │
   ├── 用户输入搜索关键词
   │      searchEvents(searchQuery)
   │      → 过滤：ticker_name.toLowerCase().includes(query)
   │              || theme.toLowerCase().includes(query)
   │              || headline.toLowerCase().includes(query)
   │      → 返回过滤后数组，重新渲染
   │
   ├── 用户点击筛选标签
   │      natureFilter = 'positive' | 'negative' | 'risk' | null
   │      → 过滤：events.filter(e => e.nature === natureFilter)
   │      → 重新渲染
   │
   └── 用户点击卡片
          onClick(event) → setSelectedEvent(event) → setDetailOpen(true)
          → 打开 EventDetail Sheet（双 Tab：脉络 + 其他说法）
```

### 3.2 参谋 Tab 数据流

```
用户打开"参谋"Tab
   │
   ├── 组件挂载：AdvisorPage.tsx
   │      初始化 messages 数组（包含欢迎语）
   │
   ├── 用户输入查询
   │      示例："宁德时代最近有什么大事"
   │      → 添加用户消息到 messages
   │      → setIsLoading(true)
   │
   ├── 模拟 Agent 处理（前端搜索）
   │      setTimeout(() => {
   │        const results = searchEvents(input)
   │        // 关键词匹配："宁德时代" → ticker_name / ticker / theme / headline
   │      }, 800)
   │
   ├── Agent 回复
   │      若 results.length > 0:
   │        → 添加 assistant 消息到 messages
   │        → message.eventCards = results.slice(0, 3)
   │      若 results.length === 0:
   │        → 添加 assistant 消息："未查询到相关事件，建议..."
   │
   └── 用户点击卡片中的"查看详情"
          → 与发现 Tab 共用同一 EventDetail 组件
          → 打开 Sheet 展示双 Tab 详情
```

### 3.3 我的 Tab 数据流

```
用户打开"我的"Tab
   │
   ├── 组件挂载：ProfilePage.tsx
   │      useEffect(() => { refreshUser() }, [])
   │      → getUser() → localStorage.getItem('eventsentry_user')
   │      → isLoggedIn() → localStorage.getItem('eventsentry_logged_in')
   │
   ├── 未登录状态
   │      loggedIn === false
   │      → setLoginOpen(true) → 弹出注册 Dialog
   │
   ├── 注册流程
   │      用户输入昵称 → 点击"开始使用"
   │      → registerUser(nickname)
   │      → 生成 User 对象 → localStorage.setItem('eventsentry_user', json)
   │      → localStorage.setItem('eventsentry_logged_in', 'true')
   │      → refreshUser() → 渲染个人主页
   │
   ├── 已登录状态
   │      渲染：头像、昵称、ID、风险偏好 Badge、持仓数量
   │      渲染：菜单列表（关注事件/关注股票/消息通知/风险偏好）
   │      渲染：持仓列表（可删除）
   │      渲染：添加持仓按钮
   │
   ├── 添加持仓
   │      点击"+ 添加" → setAddHoldingOpen(true)
   │      输入 ticker + ticker_name → 点击"添加"
   │      → addHolding(ticker, ticker_name)
   │      → user.holdings.push(newHolding)
   │      → localStorage.setItem('eventsentry_user', updatedUser)
   │      → refreshUser() → 重新渲染持仓列表
   │
   ├── 修改风险偏好
   │      点击"风险偏好" → setSettingsOpen(true)
   │      选择 conservative/moderate/aggressive
   │      → updatePreferences({ risk_level })
   │      → localStorage.setItem('eventsentry_user', updatedUser)
   │      → refreshUser() → Badge 更新
   │
   └── 退出登录
          → logout() → localStorage.removeItem('eventsentry_logged_in')
          → refreshUser() → 弹出注册 Dialog
```

---

## 四、用户数据持久化流

```
用户操作触发状态变更
   │
   ├── 添加持仓
   │      addHolding("300750.SZ", "宁德时代")
   │      → getUser() 读取当前用户
   │      → user.holdings.push({id, ticker, ticker_name})
   │      → user.subscriptions.tickers.push(ticker)  // 自动订阅标的
   │      → setUser(user) → localStorage.setItem('eventsentry_user', JSON.stringify(user))
   │      → 返回更新后的 user，组件重新渲染
   │
   ├── 关注事件
   │      subscribeEvent("300750_SZ_储能业务扩张")
   │      → getUser() 读取当前用户
   │      → user.subscriptions.events.push(eventId)
   │      → setUser(user) → localStorage 写入
   │      → EventDetail 中 BookmarkCheck 图标变为填充态
   │
   ├── 修改偏好
   │      updatePreferences({ risk_level: 'aggressive' })
   │      → getUser() 读取当前用户
   │      → user.preferences.risk_level = 'aggressive'
   │      → setUser(user) → localStorage 写入
   │      → ProfilePage 中风险偏好 Badge 更新
   │
   └── 页面刷新
          → ProfilePage useEffect 读取 localStorage
          → getUser() 返回持久化数据
          → 用户状态不丢失
```

---

## 五、关键数据转换节点

### Node 1: iFinD CSV → 标准化公告（构建期）

```typescript
// 输入：iFinD CSV 原始数据
// 处理：Python csv.DictReader 解析
// 输出：标准化公告对象

interface RawAnnouncement {
  reportDate: string;      // "2025-09-15"
  reportTitle: string;     // "2025年半年度报告"
  // ... 其他字段
}
```

### Node 2: 标准化公告 → 事件证据（构建期，人工结构化）

```typescript
// 输入：同一主题的多条公告
// 处理：人工聚类 + 规则分级
// 输出：EvidenceItem

interface EvidenceItem {
  source: string;          // "公司公告"
  date: string;            // "2025-09-15"
  summary: string;         // "2025年半年报：储能业务收入同比增长35.2%"
  url: string;             // "#" (V1 占位)
}
```

### Node 3: 证据 → 状态标签（构建期，规则判定）

```typescript
function evaluateStatus(evidence: Evidence[]): string {
  const t0 = evidence.filter(e => e.tier === 'T0');
  const t1 = evidence.filter(e => e.tier === 'T1');
  
  if (t0.length > 0) return '官方确认';
  if (t1.length >= 2) return '媒体验证';
  return '未证实传闻';
}
```

### Node 4: 事件 → Face 卡片（运行时，组件渲染）

```typescript
// 输入：EventCard 对象
// 处理：EventCardItem 组件渲染
// 输出：DOM 节点

// 渲染逻辑：
// 1. nature → 颜色（positive=green, negative=red, risk=orange, neutral=gray）
// 2. status → Badge 背景色
// 3. timeline → 横向圆点连线，is_current 高亮
// 4. headline → 文本截断（line-clamp-2）
```

### Node 5: 事件 → Back 卡片（运行时，用户点击触发）

```typescript
// 输入：EventCard 对象
// 处理：EventDetail 组件渲染（Tab 切换）
// 输出：Sheet 弹窗 DOM

// Tab 1（事件脉络）：
//   - timeline 按年份分组
//   - 超 1 年节点折叠
//   - evidence 按 T0/T1/T2/T3 分层展示
//
// Tab 2（其他说法）：
//   - directions 渲染为概率卡片
//   - rumors 独立区域，灰色弱化展示
```

---

## 六、时间戳处理

```
原始公告数据
   │
   ├── 披露时间 (publish_time)
   │      └── 公告发布日期（状态演化主轴排序依据）
   │      └── 示例：reportDate = "2025-09-15"
   │
   ├── 事件发生时间 (event_time)
   │      └── 从标题/内容中抽取（如"公司于上周签订协议"）
   │      └── 若无法抽取，使用披露时间作为近似
   │
   ├── 抓取时间 (crawl_time)
   │      └── Python 脚本执行时间
   │      └── 用于数据溯源
   │
   └── 更新时间 (updated_at)
         └── 事件最后状态变化的时间
         └── 用户可见的"最后更新"标识
         └── 发现 Tab 排序依据
```

**时间折叠规则（UI 层）：**
- 事件跨度 ≤ 6 个月：全部节点展开显示；
- 6 个月 < 跨度 ≤ 1 年：早期节点缩小显示；
- 跨度 > 1 年：早期节点折叠为"··· 2023年及更早 ···"，点击展开。

---

## 七、V2 实时数据流（后端化后启用）

V1 纯静态架构的数据局限：
- 数据无法实时更新（需重新构建）
- 用户数据无法跨设备同步
- 无法支持推送通知

V2 目标数据流：

```
┌─────────────────────────────────────────────────────────────────────┐
│                        V2 实时数据流（目标）                          │
│                                                                      │
│   Collector Agent（每 5 分钟）                                       │
│      → iFinD MCP 抓取 → 去重 → RawMessageQueue                     │
│                                                                      │
│   Analyst Agent（消费队列）                                          │
│      → 语义聚类 → 证据分级 → 状态跃迁判断 → 卡片生成               │
│      → 写入 PostgreSQL（EventDB）                                   │
│                                                                      │
│   前端（WebSocket / SSE）                                            │
│      → 订阅事件更新 → 实时推送状态跃迁通知                           │
│                                                                      │
│   用户对话（参谋 Tab）                                               │
│      → POST /api/v1/chat → LLM 理解意图 → 查询 EventDB             │
│      → 返回卡片 + 引用证据                                           │
└─────────────────────────────────────────────────────────────────────┘
```
