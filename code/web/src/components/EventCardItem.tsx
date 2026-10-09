import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ArrowRight, Clock, TrendingUp, TrendingDown, AlertTriangle, Minus } from 'lucide-react';
import type { EventCard } from '@/types';

interface Props {
  event: EventCard;
  onClick: (event: EventCard) => void;
}

const natureColors: Record<string, { bg: string; text: string; icon: React.ReactNode }> = {
  positive: { bg: 'bg-green-50', text: 'text-green-700', icon: <TrendingUp className="w-3.5 h-3.5" /> },
  negative: { bg: 'bg-red-50', text: 'text-red-700', icon: <TrendingDown className="w-3.5 h-3.5" /> },
  neutral: { bg: 'bg-gray-50', text: 'text-gray-700', icon: <Minus className="w-3.5 h-3.5" /> },
  risk: { bg: 'bg-orange-50', text: 'text-orange-700', icon: <AlertTriangle className="w-3.5 h-3.5" /> },
};

const statusColors: Record<string, string> = {
  '未证实传闻': 'bg-gray-100 text-gray-600',
  '媒体验证': 'bg-blue-100 text-blue-600',
  '官方确认': 'bg-emerald-100 text-emerald-600',
  '官方否认': 'bg-red-100 text-red-600',
  '实质落地': 'bg-purple-100 text-purple-600',
  '已过期': 'bg-gray-100 text-gray-400',
};

export default function EventCardItem({ event, onClick }: Props) {
  const nature = natureColors[event.nature] || natureColors.neutral;
  const currentNode = event.timeline.find(t => t.is_current) || event.timeline[event.timeline.length - 1];

  return (
    <Card 
      className="mb-3 cursor-pointer hover:shadow-md transition-shadow active:scale-[0.98] border-l-4"
      style={{ borderLeftColor: event.nature === 'positive' ? '#22c55e' : event.nature === 'negative' ? '#ef4444' : event.nature === 'risk' ? '#f97316' : '#9ca3af' }}
      onClick={() => onClick(event)}
    >
      <CardContent className="p-4">
        {/* Header */}
        <div className="flex items-start justify-between mb-2">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant="outline" className={`${nature.bg} ${nature.text} border-0 flex items-center gap-1 text-xs font-medium`}>
              {nature.icon}
              {event.nature_label}
            </Badge>
            <Badge variant="outline" className={`${statusColors[event.status] || 'bg-gray-100 text-gray-600'} border-0 text-xs`}>
              {event.status}
            </Badge>
          </div>
          <div className="flex items-center text-xs text-gray-400">
            <Clock className="w-3 h-3 mr-1" />
            {event.updated_at}
          </div>
        </div>

        {/* Title */}
        <h3 className="text-sm font-semibold text-gray-900 mb-1 line-clamp-2">
          {event.ticker_name} · {event.theme}
        </h3>
        <p className="text-xs text-gray-600 mb-3 line-clamp-2 leading-relaxed">
          {event.headline}
        </p>

        {/* Timeline mini */}
        <div className="flex items-center gap-1 mb-3">
          {event.timeline.map((node, idx) => (
            <div key={idx} className="flex items-center">
              <div className={`w-2 h-2 rounded-full ${node.is_current ? 'bg-blue-500 ring-2 ring-blue-200' : 'bg-gray-300'}`} />
              {idx < event.timeline.length - 1 && (
                <div className="w-4 h-px bg-gray-200 mx-1" />
              )}
            </div>
          ))}
          <span className="text-xs text-blue-600 ml-2 font-medium">{currentNode?.label}</span>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-400">{event.ticker}</span>
          <div className="flex items-center text-xs text-blue-600 font-medium">
            详情
            <ArrowRight className="w-3 h-3 ml-1" />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
