import { useState } from 'react';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  ArrowLeft, Bookmark, BookmarkCheck, AlertTriangle, TrendingUp, TrendingDown, Minus,
  ChevronRight, Shield, Newspaper, FileText, MessageSquare, Eye
} from 'lucide-react';
import { trpc } from '@/providers/trpc';
import { adaptEvent, type EventCard } from '@/types';
import EvidenceBar from './EvidenceBar';
import EventVersionTimeline from './EventVersionTimeline';

interface Props {
  event: EventCard | null;
  isOpen: boolean;
  onClose: () => void;
}

const natureConfig: Record<string, { color: string; icon: React.ReactNode; bg: string }> = {
  positive: { color: 'text-green-700', icon: <TrendingUp className="w-4 h-4" />, bg: 'bg-green-50' },
  negative: { color: 'text-red-700', icon: <TrendingDown className="w-4 h-4" />, bg: 'bg-red-50' },
  neutral: { color: 'text-gray-700', icon: <Minus className="w-4 h-4" />, bg: 'bg-gray-50' },
  risk: { color: 'text-orange-700', icon: <AlertTriangle className="w-4 h-4" />, bg: 'bg-orange-50' },
};

const tierConfig = {
  T0: { label: '官方披露', color: 'bg-emerald-500', icon: <Shield className="w-3 h-3" /> },
  T1: { label: '权威媒体', color: 'bg-blue-500', icon: <Newspaper className="w-3 h-3" /> },
  T2: { label: '研报观点', color: 'bg-amber-500', icon: <FileText className="w-3 h-3" /> },
  T3: { label: '市场传闻', color: 'bg-gray-400', icon: <MessageSquare className="w-3 h-3" /> },
};

const statusColors: Record<string, string> = {
  '未证实传闻': 'bg-gray-100 text-gray-600',
  '媒体验证': 'bg-blue-100 text-blue-600',
  '官方确认': 'bg-emerald-100 text-emerald-600',
  '官方否认': 'bg-red-100 text-red-600',
  '实质落地': 'bg-purple-100 text-purple-600',
  '已过期': 'bg-gray-100 text-gray-400',
};

export default function EventDetail({ event, isOpen, onClose }: Props) {
  const [activeTab, setActiveTab] = useState('timeline');
  const [foldedYears, setFoldedYears] = useState<Set<string>>(new Set());

  // 调用后端 API 获取详情数据
  const { data: timelineNodes } = trpc.event.timeline.useQuery(
    { eventId: event?.id || '' },
    { enabled: !!event }
  );
  const { data: evidenceList } = trpc.event.evidence.useQuery(
    { eventId: event?.id || '' },
    { enabled: !!event }
  );
  const { data: directionsList } = trpc.event.directions.useQuery(
    { eventId: event?.id || '' },
    { enabled: !!event }
  );

  // 订阅功能
  const utils = trpc.useUtils();
  const subscribe = trpc.subscription.subscribeEvent.useMutation({
    onSuccess: () => utils.event.byId.invalidate({ eventId: event?.id }),
  });
  const unsubscribe = trpc.subscription.unsubscribeEvent.useMutation({
    onSuccess: () => utils.event.byId.invalidate({ eventId: event?.id }),
  });

  if (!event) return null;

  const nature = natureConfig[event.nature] || natureConfig.neutral;

  const toggleFold = (year: string) => {
    setFoldedYears((prev) => {
      const next = new Set(prev);
      if (next.has(year)) next.delete(year);
      else next.add(year);
      return next;
    });
  };

  // 按年份分组时间线
  const timelineByYear: Record<string, typeof event.timeline> = {};
  event.timeline.forEach((node) => {
    const year = node.date.substring(0, 4);
    if (!timelineByYear[year]) timelineByYear[year] = [];
    timelineByYear[year].push(node);
  });

  // 按 tier 分组证据
  const evidenceByTier: Record<string, typeof evidenceList> = {
    T0: evidenceList?.filter((e) => e.tier === 'T0') || [],
    T1: evidenceList?.filter((e) => e.tier === 'T1') || [],
    T2: evidenceList?.filter((e) => e.tier === 'T2') || [],
    T3: evidenceList?.filter((e) => e.tier === 'T3') || [],
  };

  return (
    <Sheet open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="bottom" className="h-[92vh] p-0 flex flex-col rounded-t-2xl">
        <SheetHeader className="px-4 pt-4 pb-2 border-b shrink-0">
          <div className="flex items-center justify-between">
            <Button variant="ghost" size="sm" className="p-0 h-8 w-8" onClick={onClose}>
              <ArrowLeft className="w-5 h-5" />
            </Button>
            <SheetTitle className="text-base font-semibold">事件详情</SheetTitle>
            <Button
              variant="ghost"
              size="sm"
              className="p-0 h-8 w-8"
              onClick={() => {
                // TODO: 检查是否已订阅
                subscribe.mutate({ eventId: event.id });
              }}
            >
              <Bookmark className="w-5 h-5 text-gray-400" />
            </Button>
          </div>
        </SheetHeader>

        <ScrollArea className="flex-1">
          <div className="px-4 py-4">
            {/* Event Header Card */}
            <div className={`rounded-xl p-4 mb-4 ${nature.bg}`}>
              <div className="flex items-center gap-2 mb-2">
                <Badge
                  variant="outline"
                  className={`${nature.color} border-0 bg-white/80 flex items-center gap-1 text-xs`}
                >
                  {nature.icon}
                  {event.nature_label}
                </Badge>
                <Badge
                  variant="outline"
                  className={`${statusColors[event.status] || 'bg-gray-100 text-gray-600'} border-0 text-xs`}
                >
                  {event.status}
                </Badge>
              </div>
              <h2 className="text-lg font-bold text-gray-900 mb-1">
                {event.ticker_name} · {event.theme}
              </h2>
              <p className="text-sm text-gray-700 leading-relaxed">{event.headline}</p>
              <div className="flex items-center justify-between mt-3">
                <span className="text-xs text-gray-500">{event.ticker}</span>
                <span className="text-xs text-gray-400">更新于 {event.updated_at}</span>
              </div>
            </div>

            {/* 证据权重可视化 */}
            <div className="mb-4">
              <EvidenceBar eventId={event.id} />
            </div>

            {/* 版本演化 */}
            <div className="mb-4">
              <EventVersionTimeline eventId={event.id} />
            </div>

            {/* Tabs */}
            <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
              <TabsList className="w-full grid grid-cols-2 mb-4">
                <TabsTrigger value="timeline">事件脉络</TabsTrigger>
                <TabsTrigger value="directions">其他说法</TabsTrigger>
              </TabsList>

              <TabsContent value="timeline" className="mt-0">
                <div className="space-y-4">
                  {/* Legend */}
                  <div className="flex flex-wrap gap-2 mb-2">
                    {Object.entries(tierConfig).map(([key, cfg]) => (
                      <div key={key} className="flex items-center gap-1 text-xs text-gray-500">
                        <div className={`w-2.5 h-2.5 rounded-full ${cfg.color}`} />
                        {cfg.label}
                      </div>
                    ))}
                  </div>

                  {/* Timeline nodes */}
                  <div className="relative pl-6 border-l-2 border-gray-200 space-y-6">
                    {Object.entries(timelineByYear).map(([year, nodes]) => {
                      const isFolded =
                        foldedYears.has(year) &&
                        nodes[0].date.substring(0, 4) !== new Date().getFullYear().toString();
                      const isOld = parseInt(year) < new Date().getFullYear() - 1;

                      return (
                        <div key={year}>
                          {isOld && (
                            <button
                              onClick={() => toggleFold(year)}
                              className="flex items-center gap-1 text-xs text-gray-400 mb-2 hover:text-gray-600"
                            >
                              <ChevronRight
                                className={`w-3 h-3 transition-transform ${isFolded ? '' : 'rotate-90'}`}
                              />
                              {year}年 ({nodes.length}个节点)
                              {isFolded && ' — 已折叠'}
                            </button>
                          )}
                          {(!isFolded || !isOld) &&
                            nodes.map((node, idx) => {
                              const tier = tierConfig[node.tier];
                              return (
                                <div key={idx} className="relative mb-4">
                                  <div
                                    className={`absolute -left-[29px] w-5 h-5 rounded-full flex items-center justify-center ${tier.color} ${
                                      node.is_current ? 'ring-2 ring-offset-2 ring-blue-400' : ''
                                    }`}
                                  >
                                    <div className="text-white">{tier.icon}</div>
                                  </div>
                                  <div
                                    className={`rounded-lg p-3 ${
                                      node.is_current ? 'bg-blue-50 border border-blue-100' : 'bg-gray-50'
                                    }`}
                                  >
                                    <div className="flex items-center gap-2 mb-1">
                                      <span className="text-xs font-medium text-gray-900">{node.label}</span>
                                      <span className="text-xs text-gray-400">{node.date}</span>
                                      <Badge
                                        variant="outline"
                                        className={`${tier.color.replace('bg-', 'text-')} border-0 bg-white text-[10px] px-1 py-0`}
                                      >
                                        {node.tier}
                                      </Badge>
                                    </div>
                                    <p className="text-xs text-gray-600">{node.summary}</p>
                                  </div>
                                </div>
                              );
                            })}
                        </div>
                      );
                    })}
                  </div>

                  {/* Evidence from API */}
                  <div className="mt-6 space-y-3">
                    <h4 className="text-sm font-semibold text-gray-900">证据详情</h4>
                    {(['T0', 'T1', 'T2', 'T3'] as const).map((tier) => {
                      const items = evidenceByTier[tier];
                      if (!items || items.length === 0) return null;
                      const cfg = tierConfig[tier];
                      return (
                        <div key={tier} className="rounded-lg border border-gray-100 overflow-hidden">
                          <div
                            className={`${cfg.color} text-white px-3 py-1.5 flex items-center gap-1.5 text-xs font-medium`}
                          >
                            {cfg.icon}
                            {cfg.label} ({items.length})
                          </div>
                          <div className="divide-y divide-gray-50">
                            {items.map((item, idx) => (
                              <div key={idx} className="px-3 py-2.5">
                                <div className="flex items-center justify-between mb-1">
                                  <span className="text-xs font-medium text-gray-800">{item.source}</span>
                                  <span className="text-xs text-gray-400">{item.date}</span>
                                </div>
                                <p className="text-xs text-gray-600">{item.summary}</p>
                              </div>
                            ))}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </TabsContent>

              <TabsContent value="directions" className="mt-0 space-y-4">
                {/* Evolution directions from API */}
                <div>
                  <h4 className="text-sm font-semibold text-gray-900 mb-3">演化方向</h4>
                  <div className="space-y-3">
                    {(directionsList || event.directions).map((dir, idx) => (
                      <div key={idx} className="rounded-xl border border-gray-100 p-4">
                        <div className="flex items-start justify-between mb-2">
                          <div className="flex items-center gap-2">
                            <Badge
                              className={`${
                                dir.probability === '高'
                                  ? 'bg-green-100 text-green-700'
                                  : dir.probability === '中高'
                                    ? 'bg-emerald-100 text-emerald-700'
                                    : 'bg-amber-100 text-amber-700'
                              } border-0 text-xs`}
                            >
                              {dir.probability}概率
                            </Badge>
                            <span className="text-sm font-semibold text-gray-900">{dir.label}</span>
                          </div>
                        </div>
                        <p className="text-xs text-gray-600 mb-2">{dir.description}</p>
                        <div className="space-y-1">
                          <div className="flex items-start gap-1">
                            <TrendingUp className="w-3 h-3 text-green-500 mt-0.5 shrink-0" />
                            <span className="text-xs text-gray-500">依据: {dir.supporting.join('、')}</span>
                          </div>
                          <div className="flex items-start gap-1">
                            <AlertTriangle className="w-3 h-3 text-orange-400 mt-0.5 shrink-0" />
                            <span className="text-xs text-gray-500">风险: {dir.risk}</span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Rumors section */}
                {event.rumors && event.rumors.length > 0 && (
                  <div>
                    <h4 className="text-sm font-semibold text-gray-900 mb-3 flex items-center gap-1">
                      <Eye className="w-4 h-4 text-gray-400" />
                      独立传闻区
                    </h4>
                    <div className="space-y-2">
                      {event.rumors.map((rumor, idx) => (
                        <div key={idx} className="rounded-lg bg-gray-50 border border-gray-100 p-3">
                          <div className="flex items-center gap-2 mb-1">
                            <Badge variant="outline" className="text-gray-400 border-gray-200 text-[10px]">
                              未证实
                            </Badge>
                            <span className="text-xs text-gray-400">来源: {rumor.source}</span>
                            <span className="text-xs text-gray-400">可信度: {rumor.credibility}</span>
                          </div>
                          <p className="text-xs text-gray-600 mb-1">{rumor.content}</p>
                          <p className="text-xs text-gray-400 italic">{rumor.note}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </TabsContent>
            </Tabs>
          </div>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}
