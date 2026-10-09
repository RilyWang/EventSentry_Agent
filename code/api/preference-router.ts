import { z } from "zod";
import { createRouter, authedQuery } from "./middleware";
import { getDb } from "./queries/connection";
import { userPreferences, eventSubscriptions } from "@db/schema";
import { eq, and } from "drizzle-orm";

export const preferenceRouter = createRouter({
  get: authedQuery.query(async ({ ctx }) => {
    const db = getDb();
    const rows = await db
      .select()
      .from(userPreferences)
      .where(eq(userPreferences.userId, ctx.user.id))
      .limit(1);
    return rows[0] ?? null;
  }),

  update: authedQuery
    .input(
      z.object({
        riskLevel: z.enum(["conservative", "moderate", "aggressive"]).optional(),
        notificationEnabled: z.boolean().optional(),
      })
    )
    .mutation(async ({ ctx, input }) => {
      const db = getDb();
      const userId = ctx.user.id;

      const existing = await db
        .select()
        .from(userPreferences)
        .where(eq(userPreferences.userId, userId))
        .limit(1);

      if (existing.length > 0) {
        await db
          .update(userPreferences)
          .set({
            ...input,
            updatedAt: new Date(),
          })
          .where(eq(userPreferences.userId, userId));
      } else {
        await db.insert(userPreferences).values({
          userId,
          riskLevel: input.riskLevel ?? "moderate",
          notificationEnabled: input.notificationEnabled ?? true,
        });
      }

      const updated = await db
        .select()
        .from(userPreferences)
        .where(eq(userPreferences.userId, userId))
        .limit(1);

      return updated[0];
    }),
});

export const subscriptionRouter = createRouter({
  listEvents: authedQuery.query(async ({ ctx }) => {
    const db = getDb();
    return db
      .select()
      .from(eventSubscriptions)
      .where(eq(eventSubscriptions.userId, ctx.user.id));
  }),

  subscribeEvent: authedQuery
    .input(z.object({ eventId: z.string() }))
    .mutation(async ({ ctx, input }) => {
      const db = getDb();
      const userId = ctx.user.id;

      const existing = await db
        .select()
        .from(eventSubscriptions)
        .where(and(eq(eventSubscriptions.userId, userId), eq(eventSubscriptions.eventId, input.eventId)))
        .limit(1);

      if (existing.length > 0) return existing[0];

      const result = await db.insert(eventSubscriptions).values({
        userId,
        eventId: input.eventId,
      }).$returningId();

      const rows = await db
        .select()
        .from(eventSubscriptions)
        .where(eq(eventSubscriptions.id, result[0].id))
        .limit(1);

      return rows[0];
    }),

  unsubscribeEvent: authedQuery
    .input(z.object({ eventId: z.string() }))
    .mutation(async ({ ctx, input }) => {
      const db = getDb();
      await db
        .delete(eventSubscriptions)
        .where(and(eq(eventSubscriptions.userId, ctx.user.id), eq(eventSubscriptions.eventId, input.eventId)));
      return { success: true };
    }),
});
