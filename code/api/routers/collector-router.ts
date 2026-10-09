import { z } from "zod";
import { createRouter, publicQuery, adminQuery } from "../middleware";
import { getDb } from "../queries/connection";
import { rawMessages } from "../../db/schema";
import { eq, desc } from "drizzle-orm";
import { triggerManualCollection } from "../../task-runner/collector";

export const collectorRouter = createRouter({
  /**
   * 手动触发采集（管理员）
   */
  collect: adminQuery
    .input(
      z.object({
        tickers: z.array(z.string()).optional(),
        days: z.number().min(1).max(90).default(7),
      }).optional()
    )
    .mutation(async ({ input }) => {
      const result = await triggerManualCollection(input?.tickers, input?.days);
      return result;
    }),

  /**
   * 查看原始消息队列
   */
  rawMessages: publicQuery
    .input(
      z.object({
        ticker: z.string().optional(),
        processed: z.boolean().optional(),
        limit: z.number().min(1).max(100).default(20),
        offset: z.number().min(0).default(0),
      }).optional()
    )
    .query(async ({ input }) => {
      const db = getDb();
      const conditions = [];

      if (input?.ticker) {
        conditions.push(eq(rawMessages.ticker, input.ticker));
      }
      if (input?.processed !== undefined) {
        conditions.push(eq(rawMessages.processed, input.processed));
      }

      const messages = await db
        .select()
        .from(rawMessages)
        .where(conditions.length > 0 ? conditions[0] : undefined)
        .orderBy(desc(rawMessages.createdAt))
        .limit(input?.limit || 20)
        .offset(input?.offset || 0);

      return messages;
    }),

  /**
   * 获取采集统计
   */
  stats: publicQuery.query(async () => {
    const db = getDb();
    const all = await db.select().from(rawMessages);
    const unprocessed = all.filter((m) => !m.processed).length;

    return {
      total: all.length,
      unprocessed,
      processed: all.length - unprocessed,
      byType: {
        announcement: all.filter((m) => m.sourceType === "announcement").length,
        news: all.filter((m) => m.sourceType === "news").length,
        research: all.filter((m) => m.sourceType === "research").length,
        interactive: all.filter((m) => m.sourceType === "interactive").length,
        industry: all.filter((m) => m.sourceType === "industry").length,
      },
    };
  }),
});
