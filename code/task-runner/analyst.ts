/**
 * Analyst Agent — 事件分析器
 * 职责：消费 raw_messages → 聚类 → 分级 → 状态裁决 → 卡片生成 → 通知推送
 * 触发：定时轮询 或 队列消费
 */

import { getDb } from "../api/queries/connection";
import {
  rawMessages,
  events,
  eventVersions,
  timelineNodes,
  evidenceItems,
  eventDirections,
  notifications,
  eventSubscriptions,
  sourceQuality,
} from "../db/schema";
import { eq, and, desc, inArray, like } from "drizzle-orm";
import { verifyEventImpact } from "../api/lib/fuyao";

/**
 * 分析未处理的原始消息
 */
export async function processRawMessages(limit: number = 10) {
  const db = getDb();

  // 获取未处理消息
  const messages = await db
    .select()
    .from(rawMessages)
    .where(eq(rawMessages.processed, false))
    .orderBy(desc(rawMessages.createdAt))
    .limit(limit);

  console.log(`[Analyst] Processing ${messages.length} raw messages`);

  for (const msg of messages) {
    try {
      await analyzeMessage(msg);
      await db.update(rawMessages).set({ processed: true }).where(eq(rawMessages.id, msg.id));
    } catch (err) {
      console.error(`[Analyst] Failed to process message ${msg.id}:`, err);
    }
  }

  return messages.length;
}

/**
 * 单条消息分析
 */
async function analyzeMessage(msg: typeof rawMessages.$inferSelect) {
  const db = getDb();

  // 1. 要素预抽取（简化版：从标题中提取标的+主题+动作）
  const extracted = extractEntities(msg.title, msg.ticker);

  // 2. 同一事件聚类：查找同标的、同主题、30 天窗口内的事件
  const existingEvents = await db
    .select()
    .from(events)
    .where(
      and(
        eq(events.ticker, msg.ticker),
        like(events.theme, `%${extracted.theme}%`)
      )
    );

  let event = existingEvents[0];
  const isNewEvent = !event;

  if (isNewEvent) {
    // 创建新事件
    const eventId = `${msg.ticker.replace(".", "_")}_${extracted.theme}`;
    await db.insert(events).values({
      eventId,
      ticker: msg.ticker,
      tickerName: msg.ticker, // 需要从标的数据库查名称
      theme: extracted.theme,
      headline: msg.title,
      status: msg.sourceType === "announcement" ? "官方确认" : "未证实传闻",
      nature: extracted.direction,
      natureLabel: extracted.direction === "positive" ? "利好" : extracted.direction === "negative" ? "利空" : extracted.direction === "risk" ? "风险" : "中性",
      eventTime: msg.publishTime,
      disclosureTime: msg.publishTime,
      crawlTime: new Date().toISOString().split("T")[0],
      timeline: [{
        date: msg.publishTime.slice(0, 7),
        label: msg.sourceType === "announcement" ? "官方确认" : "传闻出现",
        summary: msg.title,
        tier: classifySourceTier(msg.source, msg.sourceType),
        is_current: true,
      }],
      evidence: { T0: [], T1: [], T2: [], T3: [] },
      directions: [],
      rumors: [],
      updatedAt: msg.publishTime,
    });

    event = (await db.select().from(events).where(eq(events.eventId, eventId)))[0];

    // 创建初始版本
    const versionResult = await db.insert(eventVersions).values({
      eventId,
      version: 1,
      status: event.status,
      nature: event.nature,
      headline: event.headline,
      timelineSnapshot: event.timeline,
      evidenceSnapshot: event.evidence,
      directionsSnapshot: event.directions,
      changeType: "update",
      changeReason: "新事件创建",
    });

    await db.update(events).set({ currentVersionId: Number(versionResult.insertId) }).where(eq(events.eventId, eventId));

    console.log(`[Analyst] Created new event: ${eventId}`);
  } else {
    // 3. 状态跃迁判断
    const newTier = classifySourceTier(msg.source, msg.sourceType);
    const newStatus = evaluateStatusTransition(event.status, newTier);
    const oldStatus = event.status;

    // 4. 若状态变化，创建新版本
    if (newStatus !== oldStatus) {
      const currentVersion = await db
        .select()
        .from(eventVersions)
        .where(eq(eventVersions.eventId, event.eventId))
        .orderBy(desc(eventVersions.version))
        .limit(1);

      const nextVersion = (currentVersion[0]?.version ?? 0) + 1;

      const versionResult = await db.insert(eventVersions).values({
        eventId: event.eventId,
        version: nextVersion,
        status: newStatus,
        nature: event.nature,
        headline: msg.title,
        timelineSnapshot: event.timeline,
        evidenceSnapshot: event.evidence,
        directionsSnapshot: event.directions,
        changeType: determineChangeType(oldStatus, newStatus),
        changeReason: `${msg.source} 报道: ${msg.title.slice(0, 50)}`,
      });

      await db
        .update(events)
        .set({
          status: newStatus,
          headline: msg.title,
          currentVersionId: Number(versionResult.insertId),
          updatedAt: msg.publishTime,
        })
        .where(eq(events.eventId, event.eventId));

      // 5. 推送状态跃迁通知给订阅用户
      await pushNotification(event.eventId, newStatus, msg.title);

      console.log(`[Analyst] State transition: ${event.eventId} ${oldStatus} → ${newStatus}`);
    }

    // 6. 写入时间线节点
    await db.insert(timelineNodes).values({
      eventId: event.eventId,
      date: msg.publishTime.slice(0, 7),
      label: newStatus,
      summary: msg.title,
      tier: newTier,
      isCurrent: newStatus !== oldStatus,
      orderIndex: 999, // 简化：实际应计算正确的 order
    });

    // 7. 写入证据项
    await db.insert(evidenceItems).values({
      eventId: event.eventId,
      source: msg.source,
      sourceUrl: msg.sourceUrl || "",
      date: msg.publishTime,
      summary: msg.title,
      tier: newTier,
      rawMessageId: msg.id,
    });
  }

  // 8. 调用扶摇验证事件影响（异步，不阻塞）
  if (event) {
    verifyEventImpact(event.ticker, msg.publishTime).catch((err) => {
      console.error(`[Analyst] Fuyao verification failed:`, err);
    });
  }
}

/**
 * 要素抽取（简化规则版）
 */
function extractEntities(title: string, ticker: string) {
  // 简化实现：从标题中提取关键词作为主题
  const keywords = ["储能", "固态电池", "AI", "扩产", "销量", "动销", "合作", "收购", "分红", "回购"];
  const found = keywords.find((k) => title.includes(k));

  let direction: "positive" | "negative" | "neutral" | "risk" = "neutral";
  if (title.includes("增长") || title.includes("突破") || title.includes("确认") || title.includes("利好")) {
    direction = "positive";
  } else if (title.includes("下滑") || title.includes("亏损") || title.includes("风险") || title.includes("否认")) {
    direction = "negative";
  } else if (title.includes("传闻") || title.includes("不确定") || title.includes("待验证")) {
    direction = "risk";
  }

  return {
    theme: found || "经营动态",
    direction,
  };
}

/**
 * 来源分级
 */
function classifySourceTier(source: string, sourceType: string): "T0" | "T1" | "T2" | "T3" {
  if (sourceType === "announcement") return "T0";
  if (["财新", "第一财经", "36氪", "界面", "证券时报"].some((s) => source.includes(s))) return "T1";
  if (["证券", "研报", "中金", "中信", "国泰君安", "华泰"].some((s) => source.includes(s))) return "T2";
  return "T3";
}

/**
 * 状态跃迁规则（简化版）
 */
function evaluateStatusTransition(currentStatus: string, newTier: string): string {
  const stateMachine: Record<string, Record<string, string>> = {
    "未证实传闻": { T0: "官方确认", T1: "媒体验证", T2: "未证实传闻", T3: "未证实传闻" },
    "媒体验证": { T0: "官方确认", T1: "媒体验证", T2: "媒体验证", T3: "媒体验证" },
    "官方确认": { T0: "深化推进", T1: "官方确认", T2: "官方确认", T3: "官方确认" },
    "深化推进": { T0: "落地完成", T1: "深化推进", T2: "深化推进", T3: "深化推进" },
    "落地完成": { T0: "落地完成", T1: "落地完成", T2: "落地完成", T3: "落地完成" },
    "官方否认": { T0: "官方否认", T1: "官方否认", T2: "官方否认", T3: "官方否认" },
  };

  return stateMachine[currentStatus]?.[newTier] || currentStatus;
}

function determineChangeType(oldStatus: string, newStatus: string): "update" | "deny" | "correct" | "expire" {
  if (newStatus === "官方否认") return "deny";
  if (newStatus === "已更正") return "correct";
  if (newStatus === "已过期") return "expire";
  return "update";
}

/**
 * 推送状态跃迁通知
 */
async function pushNotification(eventId: string, newStatus: string, title: string) {
  const db = getDb();

  // 查找订阅了该事件的用户
  const subs = await db
    .select()
    .from(eventSubscriptions)
    .where(eq(eventSubscriptions.eventId, eventId));

  if (subs.length === 0) return;

  const userIds = subs.map((s) => s.userId);

  for (const userId of userIds) {
    await db.insert(notifications).values({
      userId,
      eventId,
      type: newStatus === "官方否认" ? "denial" : "state_transition",
      title: `事件状态更新：${newStatus}`,
      content: title.slice(0, 200),
      read: false,
    });
  }

  console.log(`[Analyst] Pushed ${userIds.length} notifications for ${eventId}`);
}

// CLI 入口
if (import.meta.main) {
  const limit = Number(process.argv[2]) || 10;
  processRawMessages(limit).then((count) => {
    console.log(`[Analyst] Processed ${count} messages`);
    process.exit(0);
  });
}
