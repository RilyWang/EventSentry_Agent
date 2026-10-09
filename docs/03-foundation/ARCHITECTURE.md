# 系统技术架构

> **📌 实现状态（2026-10-09 同步）**
> 本文档描述的是 **V1（纯前端静态应用）** 架构，属于历史设计。
> **当前实际架构（V2.2.0）** 为：Python FastAPI + SQLite + iFinD/同花顺 MCP + GLM-4.6，含 3 个 Agent（采集/分析/参谋）+ 确定性状态机（`server/rules/state_machine.py`）+ 合规规则层 + 反思定时任务 + 调度器。
> 代码位置：`server/`。详见 [`AGENTS.md`](../../AGENTS.md) 与 [`process.md`](../00-process/process.md) v2.2.0。
> 另：仓库 `code/` 目录保留 Hono + tRPC + Drizzle + MySQL 方案，但**未在本环境验证**（环境无 Node.js）。

> 版本：V1.0（MVP）｜ 更新日期：2025-10-08
> 
> **说明：** V1 为纯前端静态应用，所有数据在构建期获取并打包，运行时无后端服务。本文档描述 V1 实际架构，V2 后端化架构见文末"扩展路线"。

---

## 一、架构总览（纯前端静态应用）

```
┌─────────────────────────────────────────────────────────────────────┐
│                        构建期（Build Time）                          │
│                                                                      │
│   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐         │
│   │  iFinD MCP  │────▶│  Python 脚本 │────▶│ 静态 JSON   │         │
│   │  数据获取    │     │ 数据清洗/结构化│     │ events.ts   │         │
│   └─────────────┘     └─────────────┘     └─────────────┘         │
│        公告/新闻            聚类/分级          时间线/证据           │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ npm run build
┌─────────────────────────────────────────────────────────────────────┐
│                        运行时（Runtime）                             │
│                                                                      │
│   ┌──────────────────────────────────────────────────────────────┐  │
│   │              React + TypeScript + Vite（静态站点）              │  │
│   │                                                              │  │
│   │   ┌──────────┐    ┌──────────┐    ┌──────────┐             │  │
│   │   │  发现 Tab │    │  参谋 Tab │    │  我的 Tab │             │  │
│   │   │  信息流   │    │ 对话搜索  │    │ 个人主页  │             │  │
│   │   │          │    │          │    │          │             │  │
│   │   │ EventCard│    │ EventCard│    │ 持仓/关注 │             │  │
│   │   │ 列表     │    │ + 搜索   │    │ 风险偏好  │             │  │
│   │   └──────────┘    └──────────┘    └──────────┘             │  │
│   │                                                              │  │
│   │              底部导航：[发现] [参谋] [我的]                   │  │
│   │                                                              │  │
│   │   ┌─────────────────────────────────────────────────────┐   │  │
│   │   │              localStorage（浏览器本地存储）           │   │  │
│   │   │  • user: 昵称、ID、风险偏好                          │   │  │
│   │   │  • holdings: 持仓列表                               │   │  │
│   │   │  • subscriptions: 关注事件/标的                     │   │  │
│   │   └─────────────────────────────────────────────────────┘   │  │
│   └──────────────────────────────────────────────────────────────┘  │
│                                                                      │
│   部署目标：GitHub Pages / 静态 CDN（dist/ 目录）                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 二、技术栈选型

| 层级 | 技术 | 理由 |
|------|------|------|
| 前端框架 | React 19 + TypeScript + Vite | 组件化、类型安全、构建速度快 |
| 样式系统 | Tailwind CSS 3.4 + shadcn/ui | 40+ 预置组件，移动端优先，设计一致性好 |
| 状态管理 | React useState/useContext | V1 复杂度低，无需 Redux/Zustand |
| 用户存储 | localStorage | 纯静态场景下的零成本持久化 |
| 路由 | react-router v7 | 单页应用 Tab 切换 |
| 数据获取（构建期）| Python + iFinD MCP SDK | 构建前批量获取公告数据 |
| 构建工具 | Vite 7 | 快速 HMR、Tree Shaking、代码分割 |
| 部署 | GitHub Pages / 静态 CDN | 零服务器成本，任何人可访问 |

---

## 三、核心模块职责

### 3.1 数据获取层（构建期）

```
Python 脚本（/scripts/fetch_events.py）
   │
   ├── 1. 定义目标标的列表
   │      ["300750.SZ", "002594.SZ", "688981.SH", "000858.SZ", "00700.HK"]
   │
   ├── 2. 对每个标的发起 iFinD MCP 请求
   │      ifind_get_stock_announcement(ticker, start_date, end_date)
   │      ifind_get_stock_news(ticker, start_date, end_date)
   │      ifind_get_forecast(ticker, start_date, end_date)
   │
   ├── 3. 解析 CSV 返回结果
   │      提取：公告标题、发布时间、公告类型
   │
   ├── 4. 人工/规则结构化（当前 V1 阶段）
   │      聚合同一主题的多条公告 → 生成 TimelineNode[]
   │      根据来源类型分级 → T0/T1/T2/T3
   │      撰写 headline、directions、rumors
   │
   └── 5. 输出
          ├── src/data/events.ts    # TypeScript 模块（含类型 + 查询函数）
          └── src/data/events.json  # 原始 JSON 备份
```

**V1 数据边界：**
- 6 个结构化事件，覆盖 5 只热门股票
- 每个事件包含：timeline（3-5 个节点）、evidence（按 T0-T3 分层）、directions（2 个演化方向）、rumors（0-1 条）
- 数据来源：2025 年 7 月-10 月真实公告

### 3.2 前端组件层

| 组件 | 文件 | 职责 |
|------|------|------|
| **App** | `App.tsx` | 根组件，管理 activeTab 状态，三 Tab 切换容器 |
| **BottomNav** | `components/BottomNav.tsx` | 底部 Tab 导航栏（发现/参谋/我的） |
| **EventCardItem** | `components/EventCardItem.tsx` | Face 态事件卡片，用于信息流和对话结果 |
| **EventDetail** | `components/EventDetail.tsx` | 事件详情页 Sheet（双 Tab：脉络+其他说法） |
| **DiscoverPage** | `pages/DiscoverPage.tsx` | 发现 Tab：事件列表、搜索、筛选 |
| **AdvisorPage** | `pages/AdvisorPage.tsx` | 参谋 Tab：对话界面、消息列表、推荐提问 |
| **ProfilePage** | `pages/ProfilePage.tsx` | 我的 Tab：用户信息、持仓、关注、偏好 |

### 3.3 数据层（前端模块）

| 模块 | 文件 | 职责 |
|------|------|------|
| **events.ts** | `data/events.ts` | 静态事件数据 + 查询接口（getEvents、searchEvents、getEventById） |
| **userStore.ts** | `data/userStore.ts` | localStorage 用户 CRUD（register、login、holdings、preferences） |
| **types** | `types/index.ts` | TypeScript 类型定义（EventCard、User、Holding、TimelineNode 等） |

### 3.4 用户存储层（localStorage）

```typescript
// localStorage 键值设计
interface StorageSchema {
  'eventsentry_user': User;           // 用户基本信息
  'eventsentry_logged_in': 'true';    // 登录状态标记
}

interface User {
  id: string;                         // user_{timestamp}
  nickname: string;
  holdings: Holding[];                // {id, ticker, ticker_name, cost_price?}
  subscriptions: {
    tickers: string[];                // 关注的标的代码
    events: string[];                 // 关注的事件 ID
  };
  preferences: {
    risk_level: 'conservative' | 'moderate' | 'aggressive';
    notification_enabled: boolean;
  };
}
```

**读写接口：** `userStore.ts` 提供类型安全的 CRUD 函数：
- `registerUser(nickname)` → 创建用户并写入 localStorage
- `getUser()` / `setUser()` → 读写用户对象
- `addHolding(ticker, name)` / `removeHolding(id)` → 持仓管理
- `subscribeEvent(eventId)` / `unsubscribeEvent(eventId)` → 事件订阅
- `updatePreferences(prefs)` → 偏好更新

---

## 四、构建与部署流程

```
开发阶段
   │
   ├── 编辑 React 组件 / 更新事件数据
   │
   ├── npm run dev              # 本地开发服务器 http://localhost:5173
   │
   └── npm run check            # TypeScript 类型检查

构建阶段
   │
   ├── npm run build            # Vite 生产构建
   │      ├── Tree Shaking      # 移除未使用代码
   │      ├── 代码压缩          # Terser minify
   │      ├── CSS 压缩          # CSSnano
   │      └── 资源哈希          # 文件名带 content-hash
   │
   └── 输出 dist/
          ├── index.html         # 入口 HTML
          └── assets/
               ├── index-{hash}.js    # 主 JS 包（~380KB raw / ~120KB gzip）
               ├── index-{hash}.css   # 主 CSS 包（~87KB raw / ~14KB gzip）
               └── ...               # 其他静态资源

部署阶段
   │
   ├── 方式一：GitHub Pages
   │      git subtree push --prefix dist origin gh-pages
   │      # 或 GitHub Actions 自动部署
   │
   ├── 方式二：Vercel / Netlify
   │      连接 Git 仓库，自动部署 dist/
   │
   └── 方式三：CDN（阿里云 OSS / AWS S3）
          上传 dist/ 目录到对象存储，配置静态网站托管
```

---

## 五、性能与优化

| 指标 | 目标 | V1 实测 |
|------|------|---------|
| 首屏加载 | ≤ 2s | ~1.2s（gzip 后 132KB） |
| JS 包大小 | ≤ 200KB gzip | ~118KB gzip |
| CSS 包大小 | ≤ 20KB gzip | ~14KB gzip |
| 事件详情打开 | ≤ 300ms | ~150ms（前端 Sheet 动画） |
| 搜索响应 | ≤ 100ms | ~10ms（内存过滤） |

**优化手段：**
- Vite 自动 Tree Shaking：未使用的 shadcn/ui 组件不会打包
- 代码分割：按需加载（V1 单入口，V2 可拆分为按 Tab 分割）
- 静态数据内联：events.ts 直接 import，无网络请求
- localStorage 读写：异步无阻塞，用户数据即时持久化

---

## 六、安全与隐私

| 方面 | 措施 |
|------|------|
| 用户数据 | 仅存储在 localStorage，不上传服务器 |
| 敏感信息 | 不收集手机号、身份证、账户密码、资金量 |
| XSS 防护 | React 自动转义，无 dangerouslySetInnerHTML |
| 数据溯源 | 所有事件证据标注原始来源和日期 |

---

## 七、V2 扩展路线（后端化）

V1 纯前端架构的局限性：
- 数据无法实时更新（需重新构建）
- 用户数据无法跨设备同步
- 无法接入 LLM 实现真正的对话 Agent
- 无法支持推送通知

V2 目标架构：

```
前端（保留）          后端（新增）
   │                      │
   │ React App            │ Hono + tRPC API
   │ ───────────────▶     │ PostgreSQL（事件/用户数据）
   │                      │ Redis（缓存/会话）
   │                      │
   │                      │ Collector Agent（定时抓取）
   │                      │ Analyst Agent（LLM 聚类/裁决）
   │                      │ Reflector Agent（每日反思）
   │                      │
   │                      │ iFinD MCP / 扶摇 API
```

迁移路径：
1. 保留前端代码不变，将 `events.ts` 改为从后端 API 获取
2. 将 `userStore.ts` 的 localStorage 读写替换为 tRPC 调用
3. 后端实现 Collector + Analyst + Reflector Agent 流水线
4. 逐步迁移静态事件数据到 PostgreSQL
