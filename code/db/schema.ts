import {
  mysqlTable,
  mysqlEnum,
  serial,
  varchar,
  text,
  timestamp,
  bigint,
  json,
  boolean,
  int,
  decimal,
} from "drizzle-orm/mysql-core";

// ─── 用户表（OAuth 登录） ───
export const users = mysqlTable("users", {
  id: serial("id").primaryKey(),
  unionId: varchar("unionId", { length: 255 }).notNull().unique(),
  name: varchar("name", { length: 255 }),
  email: varchar("email", { length: 320 }),
  avatar: text("avatar"),
  role: mysqlEnum("role", ["user", "admin"]).default("user").notNull(),
  createdAt: timestamp("createdAt").defaultNow().notNull(),
  updatedAt: timestamp("updatedAt").defaultNow().notNull().$onUpdate(() => new Date()),
  lastSignInAt: timestamp("lastSignInAt").defaultNow().notNull(),
});

export type User = typeof users.$inferSelect;
export type InsertUser = typeof users.$inferInsert;

// ─── 事件表 ───
export const events = mysqlTable("events", {
  id: serial("id").primaryKey(),
  eventId: varchar("eventId", { length: 255 }).notNull().unique(),
  ticker: varchar("ticker", { length: 32 }).notNull(),
  tickerName: varchar("tickerName", { length: 128 }).notNull(),
  theme: varchar("theme", { length: 255 }).notNull(),
  headline: text("headline").notNull(),
  status: varchar("status", { length: 64 }).notNull(),
  nature: mysqlEnum("nature", ["positive", "negative", "neutral", "risk"]).notNull(),
  natureLabel: varchar("natureLabel", { length: 16 }).notNull(),
  // V2：四时间轴
  eventTime: varchar("eventTime", { length: 32 }), // 事件发生时间
  disclosureTime: varchar("disclosureTime", { length: 32 }), // 披露时间
  crawlTime: varchar("crawlTime", { length: 32 }), // 抓取时间
  expiresAt: varchar("expiresAt", { length: 32 }), // 过期时间
  // V2：版本控制
  currentVersionId: bigint("currentVersionId", { mode: "number", unsigned: true }),
  // V1 遗留：逐步迁移到独立表
  timeline: json("timeline").notNull(),
  evidence: json("evidence").notNull(),
  directions: json("directions").notNull(),
  rumors: json("rumors").notNull(),
  updatedAt: varchar("updatedAt", { length: 32 }).notNull(),
  createdAt: timestamp("createdAt").defaultNow().notNull(),
});

export type Event = typeof events.$inferSelect;
export type InsertEvent = typeof events.$inferInsert;

// ─── 事件版本表（版本演化快照） ───
export const eventVersions = mysqlTable("eventVersions", {
  id: serial("id").primaryKey(),
  eventId: varchar("eventId", { length: 255 }).notNull(),
  version: int("version").notNull(), // 从 1 开始递增
  status: varchar("status", { length: 64 }).notNull(),
  nature: mysqlEnum("nature", ["positive", "negative", "neutral", "risk"]).notNull(),
  headline: text("headline").notNull(),
  timelineSnapshot: json("timelineSnapshot").notNull(),
  evidenceSnapshot: json("evidenceSnapshot").notNull(),
  directionsSnapshot: json("directionsSnapshot").notNull(),
  changeType: mysqlEnum("changeType", ["update", "deny", "correct", "expire"]).notNull(),
  changeReason: text("changeReason"), // 变化原因说明
  createdBy: varchar("createdBy", { length: 64 }).notNull().default("analyst"), // analyst / manual / reflector
  createdAt: timestamp("createdAt").defaultNow().notNull(),
});

export type EventVersion = typeof eventVersions.$inferSelect;
export type InsertEventVersion = typeof eventVersions.$inferInsert;

// ─── 原始消息表（采集层输出） ───
export const rawMessages = mysqlTable("rawMessages", {
  id: serial("id").primaryKey(),
  ticker: varchar("ticker", { length: 32 }).notNull(),
  source: varchar("source", { length: 255 }).notNull(), // 来源名称
  sourceType: mysqlEnum("sourceType", ["announcement", "news", "research", "interactive", "industry"]).notNull(),
  sourceUrl: text("sourceUrl"),
  title: text("title").notNull(),
  content: text("content"), // 正文摘要
  publishTime: varchar("publishTime", { length: 32 }).notNull(), // 披露时间
  crawlTime: timestamp("crawlTime").defaultNow().notNull(), // 抓取时间
  fingerprint: varchar("fingerprint", { length: 64 }).notNull().unique(), // simhash 去重
  processed: boolean("processed").default(false).notNull(),
  assignedEventId: varchar("assignedEventId", { length: 255 }), // 聚类后归属的事件
  createdAt: timestamp("createdAt").defaultNow().notNull(),
});

export type RawMessage = typeof rawMessages.$inferSelect;
export type InsertRawMessage = typeof rawMessages.$inferInsert;

// ─── 时间线节点表（从 events.timeline JSON 拆出） ───
export const timelineNodes = mysqlTable("timelineNodes", {
  id: serial("id").primaryKey(),
  eventId: varchar("eventId", { length: 255 }).notNull(),
  date: varchar("date", { length: 32 }).notNull(),
  label: varchar("label", { length: 64 }).notNull(), // 节点状态标签
  summary: text("summary").notNull(),
  tier: mysqlEnum("tier", ["T0", "T1", "T2", "T3"]).notNull(),
  isCurrent: boolean("isCurrent").default(false).notNull(),
  orderIndex: int("orderIndex").notNull().default(0), // 排序
  createdAt: timestamp("createdAt").defaultNow().notNull(),
});

export type TimelineNode = typeof timelineNodes.$inferSelect;
export type InsertTimelineNode = typeof timelineNodes.$inferInsert;

// ─── 证据项表（从 events.evidence JSON 拆出） ───
export const evidenceItems = mysqlTable("evidenceItems", {
  id: serial("id").primaryKey(),
  eventId: varchar("eventId", { length: 255 }).notNull(),
  source: varchar("source", { length: 255 }).notNull(),
  sourceUrl: text("sourceUrl"),
  date: varchar("date", { length: 32 }).notNull(),
  summary: text("summary").notNull(),
  tier: mysqlEnum("tier", ["T0", "T1", "T2", "T3"]).notNull(),
  credibilityScore: decimal("credibilityScore", { precision: 3, scale: 2 }), // 0.00-1.00
  verified: boolean("verified").default(false).notNull(), // 是否人工核实
  rawMessageId: bigint("rawMessageId", { mode: "number", unsigned: true }), // 关联原始消息
  createdAt: timestamp("createdAt").defaultNow().notNull(),
});

export type EvidenceItem = typeof evidenceItems.$inferSelect;
export type InsertEvidenceItem = typeof evidenceItems.$inferInsert;

// ─── 演化方向表（从 events.directions JSON 拆出） ───
export const eventDirections = mysqlTable("eventDirections", {
  id: serial("id").primaryKey(),
  eventId: varchar("eventId", { length: 255 }).notNull(),
  label: varchar("label", { length: 255 }).notNull(), // 方向标题
  description: text("description").notNull(),
  probability: varchar("probability", { length: 16 }).notNull(), // 高/中高/中/低
  supporting: json("supporting").notNull(), // 支撑依据数组
  risk: text("risk").notNull(), // 风险点
  createdAt: timestamp("createdAt").defaultNow().notNull(),
});

export type EventDirection = typeof eventDirections.$inferSelect;
export type InsertEventDirection = typeof eventDirections.$inferInsert;

// ─── 来源质量表（Reflector 校准用） ───
export const sourceQuality = mysqlTable("sourceQuality", {
  id: serial("id").primaryKey(),
  sourceName: varchar("sourceName", { length: 255 }).notNull().unique(),
  sourceType: mysqlEnum("sourceType", ["T0", "T1", "T2", "T3"]).notNull(),
  totalPredictions: int("totalPredictions").notNull().default(0),
  correctPredictions: int("correctPredictions").notNull().default(0),
  hitRate: decimal("hitRate", { precision: 5, scale: 4 }).notNull().default("0.0000"), // 命中率
  lastUpdated: timestamp("lastUpdated").defaultNow().notNull().$onUpdate(() => new Date()),
});

export type SourceQuality = typeof sourceQuality.$inferSelect;
export type InsertSourceQuality = typeof sourceQuality.$inferInsert;

// ─── 通知表（状态跃迁推送） ───
export const notifications = mysqlTable("notifications", {
  id: serial("id").primaryKey(),
  userId: bigint("userId", { mode: "number", unsigned: true }).notNull(),
  eventId: varchar("eventId", { length: 255 }).notNull(),
  type: mysqlEnum("type", ["state_transition", "evidence_update", "denial", "correction", "expiry"]).notNull(),
  title: varchar("title", { length: 255 }).notNull(),
  content: text("content").notNull(),
  read: boolean("read").default(false).notNull(),
  createdAt: timestamp("createdAt").defaultNow().notNull(),
});

export type Notification = typeof notifications.$inferSelect;
export type InsertNotification = typeof notifications.$inferInsert;

// ─── 用户持仓表 ───
export const holdings = mysqlTable("holdings", {
  id: serial("id").primaryKey(),
  userId: bigint("userId", { mode: "number", unsigned: true }).notNull(),
  ticker: varchar("ticker", { length: 32 }).notNull(),
  tickerName: varchar("tickerName", { length: 128 }).notNull(),
  costPrice: varchar("costPrice", { length: 32 }),
  createdAt: timestamp("createdAt").defaultNow().notNull(),
});

export type Holding = typeof holdings.$inferSelect;
export type InsertHolding = typeof holdings.$inferInsert;

// ─── 事件订阅表 ───
export const eventSubscriptions = mysqlTable("eventSubscriptions", {
  id: serial("id").primaryKey(),
  userId: bigint("userId", { mode: "number", unsigned: true }).notNull(),
  eventId: varchar("eventId", { length: 255 }).notNull(),
  createdAt: timestamp("createdAt").defaultNow().notNull(),
});

export type EventSubscription = typeof eventSubscriptions.$inferSelect;
export type InsertEventSubscription = typeof eventSubscriptions.$inferInsert;

// ─── 标的订阅表 ───
export const tickerSubscriptions = mysqlTable("tickerSubscriptions", {
  id: serial("id").primaryKey(),
  userId: bigint("userId", { mode: "number", unsigned: true }).notNull(),
  ticker: varchar("ticker", { length: 32 }).notNull(),
  tickerName: varchar("tickerName", { length: 128 }).notNull(),
  createdAt: timestamp("createdAt").defaultNow().notNull(),
});

export type TickerSubscription = typeof tickerSubscriptions.$inferSelect;
export type InsertTickerSubscription = typeof tickerSubscriptions.$inferInsert;

// ─── 用户偏好表 ───
export const userPreferences = mysqlTable("userPreferences", {
  id: serial("id").primaryKey(),
  userId: bigint("userId", { mode: "number", unsigned: true }).notNull().unique(),
  riskLevel: mysqlEnum("riskLevel", ["conservative", "moderate", "aggressive"]).default("moderate").notNull(),
  notificationEnabled: boolean("notificationEnabled").default(true).notNull(),
  updatedAt: timestamp("updatedAt").defaultNow().notNull().$onUpdate(() => new Date()),
});

export type UserPreference = typeof userPreferences.$inferSelect;
export type InsertUserPreference = typeof userPreferences.$inferInsert;
