// ─── 前端类型定义 ───
// 后端返回 camelCase，前端组件使用 snake_case
// 通过 adaptEvent 函数做转换

export interface TimelineNode {
  date: string;
  label: string;
  summary: string;
  tier: 'T0' | 'T1' | 'T2' | 'T3';
  is_current: boolean;
}

export interface EvidenceItem {
  source: string;
  date: string;
  summary: string;
  url: string;
}

export interface Evidence {
  T0: EvidenceItem[];
  T1: EvidenceItem[];
  T2: EvidenceItem[];
  T3: EvidenceItem[];
}

export interface Direction {
  probability: string;
  label: string;
  description: string;
  supporting: string[];
  risk: string;
}

export interface Rumor {
  content: string;
  source: string;
  credibility: string;
  note: string;
}

export interface EventCard {
  id: string;
  ticker: string;
  ticker_name: string;
  theme: string;
  headline: string;
  status: string;
  nature: 'positive' | 'negative' | 'neutral' | 'risk';
  nature_label: string;
  timeline: TimelineNode[];
  evidence: Evidence;
  directions: Direction[];
  rumors: Rumor[];
  updated_at: string;
}

export interface User {
  id: string;
  nickname: string;
  avatar?: string;
  holdings: Holding[];
  subscriptions: {
    tickers: string[];
    events: string[];
  };
  preferences: {
    risk_level: 'conservative' | 'moderate' | 'aggressive';
    notification_enabled: boolean;
  };
}

export interface Holding {
  id: string;
  ticker: string;
  ticker_name: string;
  cost_price?: number;
}

export type TabType = 'discover' | 'advisor' | 'profile';

// ─── 后端数据适配器 ───
// 将后端 camelCase 转为前端 snake_case

export function adaptEvent(dbEvent: {
  eventId: string;
  ticker: string;
  tickerName: string;
  theme: string;
  headline: string;
  status: string;
  nature: 'positive' | 'negative' | 'neutral' | 'risk';
  natureLabel: string;
  timeline: any[];
  evidence: any;
  directions: any[];
  rumors: any[];
  updatedAt: string;
}): EventCard {
  return {
    id: dbEvent.eventId,
    ticker: dbEvent.ticker,
    ticker_name: dbEvent.tickerName,
    theme: dbEvent.theme,
    headline: dbEvent.headline,
    status: dbEvent.status,
    nature: dbEvent.nature,
    nature_label: dbEvent.natureLabel,
    timeline: (dbEvent.timeline || []).map((t: any) => ({
      date: t.date,
      label: t.label,
      summary: t.summary,
      tier: t.tier,
      is_current: t.is_current ?? t.isCurrent ?? false,
    })),
    evidence: dbEvent.evidence || { T0: [], T1: [], T2: [], T3: [] },
    directions: dbEvent.directions || [],
    rumors: dbEvent.rumors || [],
    updated_at: dbEvent.updatedAt,
  };
}
