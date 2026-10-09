import { relations } from "drizzle-orm";
import {
  users,
  holdings,
  eventSubscriptions,
  tickerSubscriptions,
  userPreferences,
  events,
  eventVersions,
  timelineNodes,
  evidenceItems,
  eventDirections,
  notifications,
  rawMessages,
} from "./schema";

export const usersRelations = relations(users, ({ many, one }) => ({
  holdings: many(holdings),
  eventSubscriptions: many(eventSubscriptions),
  tickerSubscriptions: many(tickerSubscriptions),
  preferences: one(userPreferences, {
    fields: [users.id],
    references: [userPreferences.userId],
  }),
  notifications: many(notifications),
}));

export const eventsRelations = relations(events, ({ many }) => ({
  versions: many(eventVersions),
  timelineNodes: many(timelineNodes),
  evidenceItems: many(evidenceItems),
  directions: many(eventDirections),
  notifications: many(notifications),
}));

export const eventVersionsRelations = relations(eventVersions, ({ one }) => ({
  event: one(events, {
    fields: [eventVersions.eventId],
    references: [events.eventId],
  }),
}));

export const timelineNodesRelations = relations(timelineNodes, ({ one }) => ({
  event: one(events, {
    fields: [timelineNodes.eventId],
    references: [events.eventId],
  }),
}));

export const evidenceItemsRelations = relations(evidenceItems, ({ one }) => ({
  event: one(events, {
    fields: [evidenceItems.eventId],
    references: [events.eventId],
  }),
  rawMessage: one(rawMessages, {
    fields: [evidenceItems.rawMessageId],
    references: [rawMessages.id],
  }),
}));

export const eventDirectionsRelations = relations(eventDirections, ({ one }) => ({
  event: one(events, {
    fields: [eventDirections.eventId],
    references: [events.eventId],
  }),
}));

export const notificationsRelations = relations(notifications, ({ one }) => ({
  user: one(users, {
    fields: [notifications.userId],
    references: [users.id],
  }),
  event: one(events, {
    fields: [notifications.eventId],
    references: [events.eventId],
  }),
}));

export const holdingsRelations = relations(holdings, ({ one }) => ({
  user: one(users, {
    fields: [holdings.userId],
    references: [users.id],
  }),
}));

export const eventSubscriptionsRelations = relations(eventSubscriptions, ({ one }) => ({
  user: one(users, {
    fields: [eventSubscriptions.userId],
    references: [users.id],
  }),
}));

export const tickerSubscriptionsRelations = relations(tickerSubscriptions, ({ one }) => ({
  user: one(users, {
    fields: [tickerSubscriptions.userId],
    references: [users.id],
  }),
}));
