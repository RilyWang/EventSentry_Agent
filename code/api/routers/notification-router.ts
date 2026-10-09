import { z } from "zod";
import { createRouter, authedQuery } from "../middleware";
import { getDb } from "../queries/connection";
import { notifications } from "../../db/schema";
import { eq, and, desc } from "drizzle-orm";

export const notificationRouter = createRouter({
  /**
   * 获取当前用户的通知列表
   */
  list: authedQuery
    .input(
      z.object({
        unreadOnly: z.boolean().default(false),
        limit: z.number().min(1).max(50).default(20),
        offset: z.number().min(0).default(0),
      }).optional()
    )
    .query(async ({ ctx, input }) => {
      const db = getDb();
      const userId = ctx.user.id;

      const conditions = [eq(notifications.userId, userId)];
      if (input?.unreadOnly) {
        conditions.push(eq(notifications.read, false));
      }

      const list = await db
        .select()
        .from(notifications)
        .where(and(...conditions))
        .orderBy(desc(notifications.createdAt))
        .limit(input?.limit || 20)
        .offset(input?.offset || 0);

      const unreadCount = await db
        .select()
        .from(notifications)
        .where(and(eq(notifications.userId, userId), eq(notifications.read, false)));

      return { list, unreadCount: unreadCount.length };
    }),

  /**
   * 标记通知为已读
   */
  markRead: authedQuery
    .input(z.object({ id: z.number() }))
    .mutation(async ({ ctx, input }) => {
      const db = getDb();
      await db
        .update(notifications)
        .set({ read: true })
        .where(
          and(eq(notifications.id, input.id), eq(notifications.userId, ctx.user.id))
        );
      return { success: true };
    }),

  /**
   * 标记所有通知为已读
   */
  markAllRead: authedQuery.mutation(async ({ ctx }) => {
    const db = getDb();
    await db
      .update(notifications)
      .set({ read: true })
      .where(eq(notifications.userId, ctx.user.id));
    return { success: true };
  }),
});
