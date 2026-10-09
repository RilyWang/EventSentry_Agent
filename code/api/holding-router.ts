import { z } from "zod";
import { createRouter, authedQuery } from "./middleware";
import { getDb } from "./queries/connection";
import { holdings, tickerSubscriptions } from "@db/schema";
import { eq, and } from "drizzle-orm";

export const holdingRouter = createRouter({
  list: authedQuery.query(async ({ ctx }) => {
    const db = getDb();
    return db
      .select()
      .from(holdings)
      .where(eq(holdings.userId, ctx.user.id));
  }),

  create: authedQuery
    .input(
      z.object({
        ticker: z.string().min(1),
        tickerName: z.string().min(1),
        costPrice: z.string().optional(),
      })
    )
    .mutation(async ({ ctx, input }) => {
      const db = getDb();
      const userId = ctx.user.id;

      // Check if already exists
      const existing = await db
        .select()
        .from(holdings)
        .where(and(eq(holdings.userId, userId), eq(holdings.ticker, input.ticker)))
        .limit(1);

      if (existing.length > 0) {
        return existing[0];
      }

      const result = await db.insert(holdings).values({
        userId,
        ticker: input.ticker,
        tickerName: input.tickerName,
        costPrice: input.costPrice,
      }).$returningId();

      const newHolding = await db
        .select()
        .from(holdings)
        .where(eq(holdings.id, result[0].id))
        .limit(1);

      // Auto-subscribe ticker
      const existingSub = await db
        .select()
        .from(tickerSubscriptions)
        .where(and(eq(tickerSubscriptions.userId, userId), eq(tickerSubscriptions.ticker, input.ticker)))
        .limit(1);

      if (existingSub.length === 0) {
        await db.insert(tickerSubscriptions).values({
          userId,
          ticker: input.ticker,
          tickerName: input.tickerName,
        });
      }

      return newHolding[0];
    }),

  delete: authedQuery
    .input(z.object({ id: z.number() }))
    .mutation(async ({ ctx, input }) => {
      const db = getDb();
      await db
        .delete(holdings)
        .where(and(eq(holdings.id, input.id), eq(holdings.userId, ctx.user.id)));
      return { success: true };
    }),
});
