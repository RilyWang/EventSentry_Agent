# API 规范

> **📌 实现状态（2026-10-09 同步）**
> 本文档描述 V1 前端模块接口与 localStorage 方案，属历史设计。
> **当前实际 API（V2.2.0，FastAPI，代码在 `server/main.py`）**：
>
> | 方法 | 路径 | 说明 |
> |------|------|------|
> | POST | `/api/chat` | 参谋 Agent 对话（真实 LLM + iFinD 工具调用），返回 `{answer, citations, tools_used, iterations}` |
> | GET | `/api/events` | 事件列表，支持 `search` / `nature` / `limit` / `offset`，返回 `{items, total}` |
> | GET | `/api/events/{id}` | 事件详情 |
> | GET | `/api/events/{id}/timeline` | 时间线节点 |
> | GET | `/api/events/{id}/evidence` | 证据（可 `tier` 筛选），含 `evidence_type` |
> | GET | `/api/events/{id}/directions` | 演化方向 |
> | GET | `/api/events/{id}/versions` | 版本快照（含 `rule_fired` 规则编号） |
> | GET | `/api/agents/status` | 多 Agent 运行状态 + 数据统计 |
> | POST | `/api/pipeline/run` | 手动触发 采集→分析 流水线 |
> | POST | `/api/reflect/run` | 手动触发反思任务 |
> | GET/POST/DELETE | `/api/subscriptions` | 事件订阅 |
> | GET/POST/DELETE | `/api/holdings` | 持仓管理 |
> | GET/POST | `/api/preferences` | 风险偏好 |
> | GET/POST | `/api/notifications` | 通知中心 |
> | GET | `/api/ping` | 健康检查 |
>
> 外部数据源接口（iFinD MCP）的实际可用性见 [`AGENTS.md`](../../AGENTS.md) 第四节。

> 版本：V1.0（MVP）｜ 更新日期：2025-10-08
> 
> **说明：** V1 为纯前端静态应用，无后端 REST API。本文档描述前端模块接口规范（TypeScript 模块 + localStorage 操作）。V2 后端化后将补充 REST API 规范。

---

## 一、外部数据源接口（构建期调用）

### iFinD MCP 工具集

V1 在构建期通过 Python 脚本调用以下 iFinD MCP 接口获取原始数据：

```typescript
// 公司公告
interface GetAnnouncementsParams {
  ticker: string;           // 如 "300750.SZ"
  start_date: string;       // "YYYY-MM-DD"
  end_date: string;         // "YYYY-MM-DD"
}

interface Announcement {
  reportDate: string;       // 公告日期
  reportTitle: string;      // 公告标题
  content?: string;         // 公告内容摘要
}

// 调用方式（Python 脚本）
// python3 /app/.agents/plugins/ifind/scripts/ifind_tool.py call \
//   --data-source ifind \
//   --api-name ifind_get_stock_announcement \
//   --params-json '{"ticker":"300750.SZ","start_date":"2025-09-01","end_date":"2025-10-08"}'
```

**V1 已调用接口：**

| API | 用途 | 输出 |
|-----|------|------|
| `ifind_get_stock_announcement` | 获取公司公告 | CSV 格式公告列表 |
| `ifind_get_stock_info` | 获取股票基本信息 | CSV 格式公司资料 |
| `ifind_get_forecast` | 获取业绩预告 | CSV 格式预告数据 |

**数据转换流程：**
```
iFinD CSV 原始数据
   ↓
Python 解析（csv.DictReader）
   ↓
人工/规则结构化（聚类同一主题公告）
   ↓
生成 TypeScript 模块 src/data/events.ts
   ↓
Vite 构建打包进产物
```

---

## 二、前端数据模块接口

### 2.1 事件数据模块（`data/events.ts`）

```typescript
// 获取全部事件（按 updated_at 倒序）
export const getEvents = (): EventCard[];

// 根据 ID 获取单个事件
export const getEventById = (id: string): EventCard | undefined;

// 根据标的代码获取事件列表
export const getEventsByTicker = (ticker: string): EventCard[];

// 搜索事件（关键词匹配 ticker_name / theme / headline / ticker）
export const searchEvents = (query: string): EventCard[];
```

**EventCard 类型定义：**

```typescript
interface EventCard {
  id: string;                    // 唯一标识，如 "300750_SZ_储能业务扩张"
  ticker: string;                // 标的代码，如 "300750.SZ"
  ticker_name: string;           // 标的名称，如 "宁德时代"
  theme: string;                 // 事件主题，如 "储能业务扩张"
  headline: string;              // 一句话摘要
  status: string;                // 状态标签："官方确认" / "媒体验证" / "未证实传闻" 等
  nature: 'positive' | 'negative' | 'neutral' | 'risk';
  nature_label: string;          // "利好" / "利空" / "中性" / "风险"
  timeline: TimelineNode[];      // 时间线节点
  evidence: Evidence;            // 按 T0-T3 分层的证据
  directions: Direction[];       // 演化方向（2-3 个）
  rumors: Rumor[];               // 独立传闻区
  updated_at: string;            // 最后更新时间，如 "2025-10-05"
}

interface TimelineNode {
  date: string;                  // 节点时间，如 "2025-09"
  label: string;                 // 节点状态，如 "官方确认"
  summary: string;               // 节点描述
  tier: 'T0' | 'T1' | 'T2' | 'T3';
  is_current: boolean;           // 是否为当前节点
}

interface Evidence {
  T0: EvidenceItem[];
  T1: EvidenceItem[];
  T2: EvidenceItem[];
  T3: EvidenceItem[];
}

interface EvidenceItem {
  source: string;                // 证据来源，如 "公司公告"
  date: string;                  // 披露日期
  summary: string;               // 内容摘要
  url: string;                   // 原文链接（V1 为占位符 #）
}

interface Direction {
  probability: string;           // "高" / "中高" / "中" / "低"
  label: string;                 // 方向标题
  description: string;           // 方向描述
  supporting: string[];          // 支撑依据列表
  risk: string;                  // 风险点
}

interface Rumor {
  content: string;               // 传闻内容
  source: string;                // 传闻来源，如 "股吧"
  credibility: string;           // "低" / "很低"
  note: string;                  // 备注，如 "尚无官方验证"
}
```

### 2.2 用户数据模块（`data/userStore.ts`）

基于 localStorage 的用户数据管理，提供类型安全的 CRUD 接口。

```typescript
// ─── 认证 ───

// 注册新用户（自动生成 ID，写入 localStorage）
export const registerUser = (nickname: string): User;

// 获取当前用户
export const getUser = (): User | null;

// 检查登录状态
export const isLoggedIn = (): boolean;

// 退出登录（清除登录标记，保留数据）
export const logout = (): void;

// ─── 持仓 ───

// 添加持仓（自动订阅该标的）
export const addHolding = (
  ticker: string,
  ticker_name: string,
  cost_price?: number
): User | null;

// 删除持仓
export const removeHolding = (holdingId: string): User | null;

// ─── 订阅 ───

// 订阅事件
export const subscribeEvent = (eventId: string): User | null;

// 取消订阅事件
export const unsubscribeEvent = (eventId: string): User | null;

// 订阅标的
export const subscribeTicker = (ticker: string): User | null;

// ─── 偏好 ───

// 更新风险偏好 / 通知设置
export const updatePreferences = (
  prefs: Partial<User['preferences']>
): User | null;
```

**User 类型定义：**

```typescript
interface User {
  id: string;                    // 如 "user_1728423456789"
  nickname: string;
  avatar?: string;
  holdings: Holding[];
  subscriptions: {
    tickers: string[];           // 关注的标的代码列表
    events: string[];            // 关注的事件 ID 列表
  };
  preferences: {
    risk_level: 'conservative' | 'moderate' | 'aggressive';
    notification_enabled: boolean;
  };
}

interface Holding {
  id: string;                    // 如 "hold_1728423456790"
  ticker: string;                // 标的代码
  ticker_name: string;           // 标的名称
  cost_price?: number;           // 成本价（选填）
}
```

### 2.3 组件 Props 接口

```typescript
// EventCardItem 组件
interface EventCardItemProps {
  event: EventCard;
  onClick: (event: EventCard) => void;
}

// EventDetail 组件（Sheet 弹窗）
interface EventDetailProps {
  event: EventCard | null;
  isOpen: boolean;
  onClose: () => void;
  isSubscribed: boolean;
  onToggleSubscribe: (eventId: string) => void;
}

// BottomNav 组件
interface BottomNavProps {
  activeTab: 'discover' | 'advisor' | 'profile';
  onTabChange: (tab: 'discover' | 'advisor' | 'profile') => void;
}
```

---

## 三、页面级状态管理

### DiscoverPage（发现 Tab）

```typescript
interface DiscoverPageState {
  searchQuery: string;           // 搜索关键词
  natureFilter: string | null;   // 筛选条件：positive / negative / risk / neutral
  selectedEvent: EventCard | null;  // 当前选中事件（用于打开详情）
  detailOpen: boolean;           // 详情 Sheet 是否打开
  subscribedEvents: Set<string>; // 已订阅事件 ID 集合
}
```

### AdvisorPage（参谋 Tab）

```typescript
interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  eventCards?: EventCard[];      // Agent 回复附带的事件卡片
}

interface AdvisorPageState {
  messages: Message[];           // 对话消息列表
  input: string;                 // 当前输入
  isLoading: boolean;            // Agent 思考中
  selectedEvent: EventCard | null;
  detailOpen: boolean;
  subscribedEvents: Set<string>;
}
```

### ProfilePage（我的 Tab）

```typescript
interface ProfilePageState {
  user: User | null;             // 当前用户信息
  loggedIn: boolean;             // 是否已登录
  loginOpen: boolean;            // 注册弹窗是否打开
  addHoldingOpen: boolean;       // 添加持仓弹窗
  settingsOpen: boolean;         // 偏好设置弹窗
}
```

---

## 四、localStorage Schema

```typescript
// 键名前缀：eventsentry_

interface LocalStorageSchema {
  'eventsentry_user': string;         // JSON 序列化的 User 对象
  'eventsentry_logged_in': 'true';    // 登录状态标记
}

// 示例：
// localStorage.getItem('eventsentry_user')
// → '{"id":"user_1728423456789","nickname":"张三","holdings":[],...}'
//
// localStorage.getItem('eventsentry_logged_in')
// → 'true'
```

---

## 五、错误处理

| 场景 | 处理方式 |
|------|---------|
| localStorage 读取失败（隐私模式）| 降级为内存存储，页面刷新后丢失 |
| localStorage 写入超限（~5MB）| 提示用户清理缓存，优先保留用户基本信息 |
| 事件 ID 不存在 | `getEventById` 返回 `undefined`，UI 显示"事件不存在" |
| 搜索无结果 | 显示空状态插画 + "试试其他关键词"提示 |
| 网络异常（V1 无网络请求）| N/A，纯静态无网络依赖 |

---

## 六、V2 REST API 预留（后端化后启用）

V2 后端化后将引入以下 REST API，前端模块接口保持不变（仅内部实现从 localStorage 改为 fetch）：

```typescript
// 参谋 Tab
POST /api/v1/chat              // 对话请求
GET  /api/v1/events/:id        // 事件详情

// 发现 Tab
GET  /api/v1/feed              // 信息流
GET  /api/v1/feed/hot          // 热门事件

// 我的 Tab
GET  /api/v1/me                // 用户信息
POST /api/v1/holdings          // 添加持仓
DELETE /api/v1/holdings/:id    // 删除持仓
POST /api/v1/subscriptions     // 订阅事件/标的
PATCH /api/v1/preferences      // 更新偏好
```
