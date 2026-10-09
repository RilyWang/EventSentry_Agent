import { z } from "zod";
import { createRouter, publicQuery } from "./middleware";
import { getDb } from "./queries/connection";
import {
  events,
  eventVersions,
  timelineNodes,
  evidenceItems,
  eventDirections,
} from "@db/schema";
import { eq, like, or, desc, and } from "drizzle-orm";

export const eventRouter = createRouter({
  list: publicQuery.query(async () => {
    const db = getDb();
    return db.select().from(events).orderBy(desc(events.updatedAt));
  }),

  byId: publicQuery
    .input(z.object({ eventId: z.string() }))
    .query(async ({ input }) => {
      const db = getDb();
      const rows = await db
        .select()
        .from(events)
        .where(eq(events.eventId, input.eventId))
        .limit(1);
      return rows[0] ?? null;
    }),

  byTicker: publicQuery
    .input(z.object({ ticker: z.string() }))
    .query(async ({ input }) => {
      const db = getDb();
      return db
        .select()
        .from(events)
        .where(eq(events.ticker, input.ticker))
        .orderBy(desc(events.updatedAt));
    }),

  search: publicQuery
    .input(z.object({ query: z.string().min(1) }))
    .query(async ({ input }) => {
      const db = getDb();
      const q = `%${input.query}%`;
      return db
        .select()
        .from(events)
        .where(
          or(
            like(events.tickerName, q),
            like(events.theme, q),
            like(events.headline, q),
            like(events.ticker, q)
          )
        )
        .orderBy(desc(events.updatedAt));
    }),

  // ─── V2 新增：版本演化 API ───

  /**
   * 获取事件的版本历史
   */
  versions: publicQuery
    .input(z.object({ eventId: z.string() }))
    .query(async ({ input }) => {
      const db = getDb();
      return db
        .select()
        .from(eventVersions)
        .where(eq(eventVersions.eventId, input.eventId))
        .orderBy(desc(eventVersions.version));
    }),

  /**
   * 对比两个版本的差异
   */
  versionDiff: publicQuery
    .input(z.object({ fromVersionId: z.number(), toVersionId: z.number() }))
    .query(async ({ input }) => {
      const db = getDb();
      const [fromV, toV] = await Promise.all([
        db.select().from(eventVersions).where(eq(eventVersions.id, input.fromVersionId)).limit(1),
        db.select().from(eventVersions).where(eq(eventVersions.id, input.toVersionId)).limit(1),
      ]);
      return {
        from: fromV[0] ?? null,
        to: toV[0] ?? null,
        changed: fromV[0]?.status !== toV[0]?.status || fromV[0]?.nature !== toV[0]?.nature,
      };
    }),

  /**
   * 获取事件的时间线节点
   */
  timeline: publicQuery
    .input(z.object({ eventId: z.string() }))
    .query(async ({ input }) => {
      const db = getDb();
      return db
        .select()
        .from(timelineNodes)
        .where(eq(timelineNodes.eventId, input.eventId))
        .orderBy(timelineNodes.orderIndex);
    }),

  /**
   * 获取事件的证据链
   */
  evidence: publicQuery
    .input(
      z.object({
        eventId: z.string(),
        tier: z.enum(["T0", "T1", "T2", "T3"]).optional(),
      })
    )
    .query(async ({ input }) => {
      const db = getDb();
      const conditions = [eq(evidenceItems.eventId, input.eventId)];
      if (input.tier) {
        conditions.push(eq(evidenceItems.tier, input.tier));
      }
      return db
        .select()
        .from(evidenceItems)
        .where(and(...conditions))
        .orderBy(desc(evidenceItems.date));
    }),

  /**
   * 获取事件的演化方向
   */
  directions: publicQuery
    .input(z.object({ eventId: z.string() }))
    .query(async ({ input }) => {
      const db = getDb();
      return db
        .select()
        .from(eventDirections)
        .where(eq(eventDirections.eventId, input.eventId))
        .orderBy(eventDirections.createdAt);
    }),
});
