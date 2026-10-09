import { useState } from 'react';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { Search, SlidersHorizontal, RefreshCw } from 'lucide-react';
import EventCardItem from '@/components/EventCardItem';
import EventDetail from '@/components/EventDetail';
import { trpc } from '@/providers/trpc';
import { adaptEvent, type EventCard } from '@/types';

export default function DiscoverPage() {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedEvent, setSelectedEvent] = useState<EventCard | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [natureFilter, setNatureFilter] = useState<string | null>(null);

  // 调用后端 API 获取真实事件列表
  const { data: dbEvents, isLoading, refetch } = trpc.event.list.useQuery();

  // 调用后端 API 搜索（当输入有内容时）
  const { data: searchResults, isLoading: searching } = trpc.event.search.useQuery(
    { query: searchQuery },
    { enabled: searchQuery.trim().length > 0 }
  );

  // 适配数据
  const allEvents = searchQuery.trim()
    ? (searchResults || []).map(adaptEvent)
    : (dbEvents || []).map(adaptEvent);

  const filteredEvents = natureFilter
    ? allEvents.filter((e) => e.nature === natureFilter)
    : allEvents;

  const handleEventClick = (event: EventCard) => {
    setSelectedEvent(event);
    setDetailOpen(true);
  };

  const natureFilters = [
    { key: 'positive', label: '利好', color: 'bg-green-50 text-green-700' },
    { key: 'negative', label: '利空', color: 'bg-red-50 text-red-700' },
    { key: 'neutral', label: '中性', color: 'bg-gray-50 text-gray-700' },
    { key: 'risk', label: '风险', color: 'bg-orange-50 text-orange-700' },
  ];

  return (
    <div className="flex flex-col h-full bg-gray-50">
      {/* Header */}
      <div className="bg-white px-4 pt-4 pb-3 border-b border-gray-100 sticky top-0 z-10">
        <div className="flex items-center justify-between mb-3">
          <h1 className="text-xl font-bold text-gray-900">发现</h1>
          <button
            onClick={() => refetch()}
            className="p-2 rounded-full hover:bg-gray-100 transition-colors"
            title="刷新"
          >
            <RefreshCw className="w-4 h-4 text-gray-400" />
          </button>
        </div>
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <Input
            placeholder="搜索股票、事件主题..."
            className="pl-9 h-10 bg-gray-50 border-gray-200 text-sm"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        {/* Filters */}
        <div className="flex items-center gap-2 mt-3 overflow-x-auto no-scrollbar">
          <SlidersHorizontal className="w-3.5 h-3.5 text-gray-400 shrink-0" />
          <button
            onClick={() => setNatureFilter(null)}
            className={`shrink-0 px-3 py-1 rounded-full text-xs font-medium transition-colors ${
              natureFilter === null ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600'
            }`}
          >
            全部
          </button>
          {natureFilters.map((f) => (
            <button
              key={f.key}
              onClick={() => setNatureFilter(natureFilter === f.key ? null : f.key)}
              className={`shrink-0 px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                natureFilter === f.key
                  ? f.color.replace('bg-', 'bg-opacity-100 ') + ' ring-2 ring-offset-1 ring-gray-200'
                  : f.color
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* Event List */}
      <ScrollArea className="flex-1 px-4 pt-3 pb-20">
        {isLoading || searching ? (
          <div className="flex flex-col items-center justify-center py-20 text-gray-400">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent mb-3" />
            <p className="text-sm">加载中...</p>
          </div>
        ) : filteredEvents.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-gray-400">
            <Search className="w-10 h-10 mb-3 opacity-30" />
            <p className="text-sm">没有找到相关事件</p>
            <p className="text-xs mt-1">试试搜索其他关键词</p>
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs text-gray-400">共 {filteredEvents.length} 个事件</span>
              <Badge variant="outline" className="text-[10px] text-gray-400 border-gray-200">
                实时更新
              </Badge>
            </div>
            {filteredEvents.map((event) => (
              <EventCardItem key={event.id} event={event} onClick={handleEventClick} />
            ))}
          </>
        )}
      </ScrollArea>

      <EventDetail
        event={selectedEvent}
        isOpen={detailOpen}
        onClose={() => setDetailOpen(false)}
      />
    </div>
  );
}
