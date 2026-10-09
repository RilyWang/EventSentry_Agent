import { useState, useRef, useEffect } from 'react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Send, Bot, User, TrendingUp, TrendingDown, AlertTriangle, Minus, Clock, ArrowRight, Lightbulb } from 'lucide-react';
import { trpc } from '@/providers/trpc';
import { adaptEvent, type EventCard } from '@/types';
import EventDetail from '@/components/EventDetail';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  eventCards?: EventCard[];
}

const suggestedQuestions = [
  '宁德时代最近有什么重要事件？',
  '比亚迪的高端车型卖得怎么样？',
  '中芯国际的扩产计划进展如何？',
  '白酒板块双节动销情况',
];

export default function AdvisorPage() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content: '你好！我是事件参谋，可以帮你追踪和分析股票相关的重要事件。\n\n你可以这样问我：\n• "宁德时代最近有什么大事？"\n• "比亚迪销量怎么样？"\n• "中芯国际扩产进度如何？"\n\n我会从数据库中检索关键事件，按可信度分层呈现。',
    },
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [selectedEvent, setSelectedEvent] = useState<EventCard | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const search = trpc.event.search.useQuery(
    { query: input },
    { enabled: false } // 手动触发
  );

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;

    const userMsg: Message = { id: 'u' + Date.now(), role: 'user', content: input };
    setMessages((prev) => [...prev, userMsg]);
    const query = input;
    setInput('');
    setIsLoading(true);

    try {
      // 调用后端搜索 API
      const results = await search.refetch({ query });
      const events = (results.data || []).map(adaptEvent);

      let response: Message;
      if (events.length > 0) {
        response = {
          id: 'a' + Date.now(),
          role: 'assistant',
          content: `找到 ${events.length} 个与"${query}"相关的事件：`,
          eventCards: events.slice(0, 3),
        };
      } else {
        response = {
          id: 'a' + Date.now(),
          role: 'assistant',
          content: '抱歉，我暂时没有查询到与该问题直接相关的事件。\n\n你可以尝试：\n• 使用股票名称（如"宁德时代"、"比亚迪"）\n• 使用股票代码（如"300750"）\n• 使用事件主题关键词（如"储能"、"扩产"）',
        };
      }
      setMessages((prev) => [...prev, response]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: 'a' + Date.now(),
          role: 'assistant',
          content: '查询出错，请稍后重试。',
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSuggestedClick = (q: string) => {
    setInput(q);
  };

  const handleEventClick = (event: EventCard) => {
    setSelectedEvent(event);
    setDetailOpen(true);
  };

  const natureConfig: Record<string, { color: string; icon: React.ReactNode; bg: string; label: string }> = {
    positive: { color: 'text-green-700', icon: <TrendingUp className="w-3.5 h-3.5" />, bg: 'bg-green-50', label: '利好' },
    negative: { color: 'text-red-700', icon: <TrendingDown className="w-3.5 h-3.5" />, bg: 'bg-red-50', label: '利空' },
    neutral: { color: 'text-gray-700', icon: <Minus className="w-3.5 h-3.5" />, bg: 'bg-gray-50', label: '中性' },
    risk: { color: 'text-orange-700', icon: <AlertTriangle className="w-3.5 h-3.5" />, bg: 'bg-orange-50', label: '风险' },
  };

  return (
    <div className="flex flex-col h-full bg-gray-50">
      {/* Header */}
      <div className="bg-white px-4 pt-4 pb-3 border-b border-gray-100 sticky top-0 z-10">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center">
            <Bot className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-gray-900">事件参谋</h1>
            <p className="text-xs text-gray-400">基于公开信息的事件追踪与分析</p>
          </div>
        </div>
      </div>

      {/* Messages */}
      <ScrollArea className="flex-1 px-4 py-3" ref={scrollRef}>
        <div className="space-y-4 pb-4">
          {messages.map((msg) => (
            <div key={msg.id} className={`flex gap-2 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              {msg.role === 'assistant' && (
                <div className="w-7 h-7 rounded-full bg-blue-100 flex items-center justify-center shrink-0 mt-1">
                  <Bot className="w-4 h-4 text-blue-600" />
                </div>
              )}
              <div
                className={`max-w-[80%] ${
                  msg.role === 'user'
                    ? 'bg-blue-600 text-white'
                    : 'bg-white text-gray-800 border border-gray-100'
                } rounded-2xl px-4 py-2.5 text-sm leading-relaxed shadow-sm`}
              >
                <div className="whitespace-pre-wrap">{msg.content}</div>

                {/* Event cards in message */}
                {msg.eventCards &&
                  msg.eventCards.map((event) => {
                    const nc = natureConfig[event.nature] || natureConfig.neutral;
                    const currentNode =
                      event.timeline.find((t) => t.is_current) || event.timeline[event.timeline.length - 1];
                    return (
                      <Card
                        key={event.id}
                        className="mt-3 cursor-pointer hover:shadow-md transition-shadow border-l-4"
                        style={{
                          borderLeftColor:
                            event.nature === 'positive'
                              ? '#22c55e'
                              : event.nature === 'negative'
                                ? '#ef4444'
                                : event.nature === 'risk'
                                  ? '#f97316'
                                  : '#9ca3af',
                        }}
                        onClick={() => handleEventClick(event)}
                      >
                        <CardContent className="p-3">
                          <div className="flex items-center gap-2 mb-1.5">
                            <Badge
                              variant="outline"
                              className={`${nc.bg} ${nc.color} border-0 flex items-center gap-1 text-[10px]`}
                            >
                              {nc.icon}
                              {nc.label}
                            </Badge>
                            <span className="text-[10px] text-gray-400">{event.status}</span>
                          </div>
                          <h4 className="text-sm font-semibold text-gray-900 mb-1">
                            {event.ticker_name} · {event.theme}
                          </h4>
                          <p className="text-xs text-gray-600 line-clamp-2 mb-2">{event.headline}</p>
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-1 text-[10px] text-gray-400">
                              <Clock className="w-3 h-3" />
                              {currentNode?.label}
                            </div>
                            <div className="flex items-center text-[10px] text-blue-600">
                              查看详情 <ArrowRight className="w-3 h-3 ml-0.5" />
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    );
                  })}
              </div>
              {msg.role === 'user' && (
                <div className="w-7 h-7 rounded-full bg-gray-200 flex items-center justify-center shrink-0 mt-1">
                  <User className="w-4 h-4 text-gray-600" />
                </div>
              )}
            </div>
          ))}

          {isLoading && (
            <div className="flex gap-2 justify-start">
              <div className="w-7 h-7 rounded-full bg-blue-100 flex items-center justify-center shrink-0">
                <Bot className="w-4 h-4 text-blue-600" />
              </div>
              <div className="bg-white border border-gray-100 rounded-2xl px-4 py-3 shadow-sm">
                <div className="flex gap-1">
                  <div className="w-2 h-2 bg-gray-300 rounded-full animate-bounce" />
                  <div className="w-2 h-2 bg-gray-300 rounded-full animate-bounce [animation-delay:0.1s]" />
                  <div className="w-2 h-2 bg-gray-300 rounded-full animate-bounce [animation-delay:0.2s]" />
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Suggested questions */}
        {messages.length <= 1 && (
          <div className="mt-6">
            <div className="flex items-center gap-1.5 mb-3 text-xs text-gray-500">
              <Lightbulb className="w-3.5 h-3.5" />
              <span>你可以这样问</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {suggestedQuestions.map((q, idx) => (
                <button
                  key={idx}
                  onClick={() => handleSuggestedClick(q)}
                  className="px-3 py-1.5 bg-white border border-gray-200 rounded-full text-xs text-gray-600 hover:border-blue-300 hover:text-blue-600 transition-colors"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}
      </ScrollArea>

      {/* Input */}
      <div className="bg-white border-t border-gray-100 px-4 py-3 pb-6 sticky bottom-0 z-10">
        <div className="flex gap-2 max-w-md mx-auto">
          <Input
            placeholder="输入股票名称或事件主题..."
            className="h-10 bg-gray-50 border-gray-200 text-sm"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
          />
          <Button
            size="icon"
            className="h-10 w-10 shrink-0 bg-blue-600 hover:bg-blue-700"
            onClick={handleSend}
            disabled={isLoading || !input.trim()}
          >
            <Send className="w-4 h-4" />
          </Button>
        </div>
        <p className="text-center text-[10px] text-gray-300 mt-2">
          本工具仅用于信息整理，不构成投资建议
        </p>
      </div>

      <EventDetail event={selectedEvent} isOpen={detailOpen} onClose={() => setDetailOpen(false)} />
    </div>
  );
}
