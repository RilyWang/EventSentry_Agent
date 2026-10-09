/**
 * Reflector Agent — 反思校准器
 * 频率：每日 02:00（cron）
 * 职责：回溯昨日跃迁判断 → 校准来源命中率 → 标记高争议事件
 */

import { getDb } from "../api/queries/connection";
import {
  eventVersions,
  events,
  evidenceItems,
  sourceQuality,
  rawMessages,
} from "../db/schema";
import { eq, gte, and, desc } from "drizzle-orm";

/**
 * 执行每日反思
 */
export async function runReflection() {
  console.log(`[Reflector] Starting daily reflection at ${new Date().toISOString()}`);

  const db = getDb();

  // 1. 获取过去 24 小时的跃迁事件
  const yesterday = new Date();
  yesterday.setDate(yesterday.getDate() - 1);
  const yesterdayStr = yesterday.toISOString().split("T")[0];

  const recentVersions = await db
    .select()
    .from(eventVersions)
    .where(gte(eventVersions.createdAt, yesterday))
    .orderBy(desc(eventVersions.createdAt));

  console.log(`[Reflector] ${recentVersions.length} state transitions in last 24h`);

  // 2. 对每个跃迁事件进行回溯
  let correctedCount = 0;
  for (const version of recentVersions) {
    const isCorrect = await verifyTransitionAccuracy(version);
    if (!isCorrect) {
      correctedCount++;
    }
  }

  // 3. 更新来源命中率
  await calibrateSourceQuality();

  // 4. 标记高争议事件
  const controversies = await findControversialEvents();

  // 5. 生成报告
  const report = {
    date: new Date().toISOString(),
    transitionsReviewed: recentVersions.length,
    correctedCount,
    controversies: controversies.map((c) => c.eventId),
    sourceQualityUpdates: await db.select().from(sourceQuality),
  };

  console.log(`[Reflector] Report:`, JSON.stringify(report, null, 2));

  // 写入文件报告
  const fs = await import("fs/promises");
  const reportPath = `../docs/08-test-reports/reflection_${new Date().toISOString().split("T")[0]}.json`;
  await fs.writeFile(reportPath, JSON.stringify(report, null, 2)).catch(() => {
    // 忽略写入错误
  });

  return report;
}

/**
 * 验证单次跃迁的准确性
 * 规则：若跃迁后 24h 内出现更高 tier 的反证，则标记为可能误判
 */
async function verifyTransitionAccuracy(version: typeof eventVersions.$inferSelect): Promise<boolean> {
  const db = getDb();

  // 获取该事件在跃迁后的新证据
  const newEvidence = await db
    .select()
    .from(evidenceItems)
    .where(
      and(
        eq(evidenceItems.eventId, version.eventId),
        gte(evidenceItems.createdAt, version.createdAt)
      )
    )
    .orderBy(desc(evidenceItems.createdAt));

  // 简化规则：若新证据 tier 高于原判断依据，且方向相反，则标记
  const conflictingEvidence = newEvidence.find((e) => {
    const tierWeight = { T0: 4, T1: 3, T2: 2, T3: 1 };
    const evidenceWeight = tierWeight[e.tier] || 0;
    // 若新证据是 T0/T1 且事件被否认，则可能有冲突
    return evidenceWeight >= 3 && version.changeType === "deny";
  });

  if (conflictingEvidence) {
    console.log(`[Reflector] Potential misjudgment: ${version.eventId} v${version.version}`);
    return false;
  }

  return true;
}

/**
 * 校准来源命中率
 */
async function calibrateSourceQuality() {
  const db = getDb();

  // 获取所有来源的预测记录
  const allEvidence = await db.select().from(evidenceItems);

  const sourceStats: Record<string, { total: number; correct: number; type: string }> = {};

  for (const ev of allEvidence) {
    const key = ev.source;
    if (!sourceStats[key]) {
      sourceStats[key] = { total: 0, correct: 0, type: ev.tier };
    }
    sourceStats[key].total++;

    // 简化：若证据对应的最终事件状态不是"官方否认"，则认为该来源"正确"
    const event = await db
      .select()
      .from(events)
      .where(eq(events.eventId, ev.eventId))
      .limit(1);

    if (event[0] && event[0].status !== "官方否认") {
      sourceStats[key].correct++;
    }
  }

  // 更新 sourceQuality 表
  for (const [sourceName, stats] of Object.entries(sourceStats)) {
    const hitRate = stats.total > 0 ? (stats.correct / stats.total).toFixed(4) : "0.0000";

    await db.insert(sourceQuality).values({
      sourceName,
      sourceType: stats.type as "T0" | "T1" | "T2" | "T3",
      totalPredictions: stats.total,
      correctPredictions: stats.correct,
      hitRate,
    }).onDuplicateKeyUpdate({
      set: {
        totalPredictions: stats.total,
        correctPredictions: stats.correct,
        hitRate,
      },
    });
  }

  console.log(`[Reflector] Calibrated ${Object.keys(sourceStats).length} sources`);
}

/**
 * 查找高争议事件：官方否认但市场仍传
 */
async function findControversialEvents() {
  const db = getDb();

  const deniedEvents = await db
    .select()
    .from(events)
    .where(eq(events.status, "官方否认"));

  const controversies = [];

  for (const event of deniedEvents) {
    // 检查否认后是否仍有 T3 传闻
    const recentRumors = await db
      .select()
      .from(rawMessages)
      .where(
        and(
          eq(rawMessages.ticker, event.ticker),
          eq(rawMessages.sourceType, "news")
        )
      )
      .orderBy(desc(rawMessages.createdAt))
      .limit(5);

    if (recentRumors.length > 0) {
      controversies.push(event);
      console.log(`[Reflector] Controversial event: ${event.eventId} (denied but still rumored)`);
    }
  }

  return controversies;
}

// CLI 入口
if (import.meta.main) {
  runReflection().then((report) => {
    console.log(`[Reflector] Done. Reviewed ${report.transitionsReviewed} transitions.`);
    process.exit(0);
  });
}
