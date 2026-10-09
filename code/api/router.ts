import { authRouter } from "./auth-router";
import { eventRouter } from "./event-router";
import { holdingRouter } from "./holding-router";
import { preferenceRouter, subscriptionRouter } from "./preference-router";
import { collectorRouter } from "./routers/collector-router";
import { fuyaoRouter } from "./routers/fuyao-router";
import { notificationRouter } from "./routers/notification-router";
import { createRouter, publicQuery } from "./middleware";

export const appRouter = createRouter({
  ping: publicQuery.query(() => ({ ok: true, ts: Date.now() })),
  auth: authRouter,
  event: eventRouter,
  holding: holdingRouter,
  preference: preferenceRouter,
  subscription: subscriptionRouter,
  collector: collectorRouter,
  fuyao: fuyaoRouter,
  notification: notificationRouter,
});

export type AppRouter = typeof appRouter;
