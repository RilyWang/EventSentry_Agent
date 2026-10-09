// @eventsentry/shared
// 前后端共享类型、Zod schemas 与常量
// Phase 3 中将逐步迁移 contracts/ 和 types/ 中的定义到这里

export const EVIDENCE_TIERS = ['T0', 'T1', 'T2', 'T3'] as const;
export type EvidenceTier = (typeof EVIDENCE_TIERS)[number];

export const EVENT_NATURES = ['positive', 'negative', 'neutral', 'risk'] as const;
export type EventNature = (typeof EVENT_NATURES)[number];

export const EVENT_STATUSES = [
  '未证实传闻',
  '媒体验证',
  '官方确认',
  '深化推进',
  '落地完成',
  '官方否认',
  '已更正',
  '已过期',
] as const;
export type EventStatus = (typeof EVENT_STATUSES)[number];

export const CHANGE_TYPES = ['update', 'deny', 'correct', 'expire'] as const;
export type ChangeType = (typeof CHANGE_TYPES)[number];

export const RISK_LEVELS = ['conservative', 'moderate', 'aggressive'] as const;
export type RiskLevel = (typeof RISK_LEVELS)[number];

// 占位：后续迁移 contracts/types.ts 和 web/src/types/index.ts 的共享部分
