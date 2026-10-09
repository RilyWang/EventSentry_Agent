import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import {
  LogOut, User, ChevronRight, Bell, BarChart3, Bookmark, Plus, X, Settings, FileText, Loader2
} from 'lucide-react';
import { trpc } from '@/providers/trpc';
import NotificationCenter from '@/components/NotificationCenter';

export default function ProfilePage() {
  const [addHoldingOpen, setAddHoldingOpen] = useState(false);
  const [newTicker, setNewTicker] = useState('');
  const [newTickerName, setNewTickerName] = useState('');
  const [settingsOpen, setSettingsOpen] = useState(false);

  const utils = trpc.useUtils();

  // 真实后端 API
  const { data: user, isLoading: userLoading } = trpc.auth.me.useQuery();
  const { data: holdings, isLoading: holdingsLoading } = trpc.holding.list.useQuery(undefined, {
    enabled: !!user,
  });
  const { data: prefs } = trpc.preference.get.useQuery(undefined, {
    enabled: !!user,
  });

  const logout = trpc.auth.logout.useMutation({
    onSuccess: () => {
      utils.invalidate();
      window.location.reload();
    },
  });

  const createHolding = trpc.holding.create.useMutation({
    onSuccess: () => {
      utils.holding.list.invalidate();
      setAddHoldingOpen(false);
      setNewTicker('');
      setNewTickerName('');
    },
  });

  const deleteHolding = trpc.holding.delete.useMutation({
    onSuccess: () => utils.holding.list.invalidate(),
  });

  const updatePref = trpc.preference.update.useMutation({
    onSuccess: () => utils.preference.get.invalidate(),
  });

  const handleAddHolding = () => {
    if (!newTicker.trim() || !newTickerName.trim()) return;
    createHolding.mutate({
      ticker: newTicker.trim(),
      tickerName: newTickerName.trim(),
    });
  };

  const handleUpdateRiskLevel = (level: 'conservative' | 'moderate' | 'aggressive') => {
    updatePref.mutate({ riskLevel: level });
  };

  const menuItems = [
    { icon: <Bookmark className="w-4 h-4" />, label: '关注事件', count: 0 },
    { icon: <BarChart3 className="w-4 h-4" />, label: '关注股票', count: 0 },
    { icon: <Bell className="w-4 h-4" />, label: '消息通知', action: () => {} },
    { icon: <Settings className="w-4 h-4" />, label: '风险偏好', action: () => setSettingsOpen(true) },
  ];

  const riskLevels = [
    { key: 'conservative' as const, label: '保守型', desc: '偏好低风险事件' },
    { key: 'moderate' as const, label: '稳健型', desc: '平衡风险与收益' },
    { key: 'aggressive' as const, label: '激进型', desc: '关注高弹性事件' },
  ];

  // 未登录状态
  if (!user && !userLoading) {
    return (
      <div className="flex flex-col h-full bg-gray-50 items-center justify-center px-4">
        <User className="w-16 h-16 text-gray-300 mb-4" />
        <p className="text-gray-500 mb-4">请先登录</p>
        <Button onClick={() => window.location.href = '/login'}>去登录</Button>
      </div>
    );
  }

  if (userLoading) {
    return (
      <div className="flex flex-col h-full bg-gray-50 items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-gray-400" />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-gray-50">
      <ScrollArea className="flex-1">
        {/* Header */}
        <div className="bg-white px-4 pt-6 pb-4 border-b border-gray-100">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-4">
              <div className="w-16 h-16 rounded-full bg-blue-100 flex items-center justify-center">
                {user?.avatar ? (
                  <img src={user.avatar} alt="" className="w-16 h-16 rounded-full" />
                ) : (
                  <User className="w-8 h-8 text-blue-600" />
                )}
              </div>
              <div className="flex-1">
                <h2 className="text-lg font-bold text-gray-900">{user?.name || '用户'}</h2>
                <p className="text-xs text-gray-400 mt-0.5">ID: {user?.id || '--'}</p>
                <div className="flex items-center gap-2 mt-2">
                  <Badge variant="outline" className="text-[10px] border-blue-200 text-blue-600 bg-blue-50">
                    {prefs?.riskLevel === 'conservative' ? '保守型' :
                     prefs?.riskLevel === 'aggressive' ? '激进型' : '稳健型'}
                  </Badge>
                  <Badge variant="outline" className="text-[10px] border-gray-200 text-gray-500">
                    持仓 {holdings?.length || 0}
                  </Badge>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <NotificationCenter />
              <Button variant="ghost" size="sm" className="p-2 h-auto text-gray-400" onClick={() => logout.mutate()}>
                <LogOut className="w-4 h-4" />
              </Button>
            </div>
          </div>
        </div>

        {/* Menu */}
        <div className="bg-white mt-2">
          {menuItems.map((item, idx) => (
            <button
              key={idx}
              onClick={item.action || (() => {})}
              className="w-full flex items-center justify-between px-4 py-3.5 border-b border-gray-50 last:border-0 hover:bg-gray-50 transition-colors"
            >
              <div className="flex items-center gap-3">
                <div className="text-gray-400">{item.icon}</div>
                <span className="text-sm text-gray-700">{item.label}</span>
              </div>
              <div className="flex items-center gap-2">
                {item.count !== undefined && (
                  <span className="text-xs text-gray-400">{item.count}</span>
                )}
                <ChevronRight className="w-4 h-4 text-gray-300" />
              </div>
            </button>
          ))}
        </div>

        {/* Holdings */}
        <div className="bg-white mt-2 px-4 py-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-gray-900">我的持仓</h3>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-xs text-blue-600"
              onClick={() => setAddHoldingOpen(true)}
            >
              <Plus className="w-3.5 h-3.5 mr-1" />
              添加
            </Button>
          </div>
          {holdingsLoading ? (
            <div className="text-center py-6">
              <Loader2 className="w-5 h-5 animate-spin mx-auto text-gray-400" />
            </div>
          ) : holdings && holdings.length > 0 ? (
            <div className="space-y-2">
              {holdings.map((h) => (
                <div
                  key={h.id}
                  className="flex items-center justify-between py-2 border-b border-gray-50 last:border-0"
                >
                  <div>
                    <div className="text-sm font-medium text-gray-900">{h.tickerName}</div>
                    <div className="text-xs text-gray-400">{h.ticker}</div>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 w-6 p-0 text-gray-300"
                    onClick={() => deleteHolding.mutate({ id: Number(h.id) })}
                  >
                    <X className="w-3.5 h-3.5" />
                  </Button>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-6 text-gray-400">
              <BarChart3 className="w-8 h-8 mx-auto mb-2 opacity-30" />
              <p className="text-xs">暂无持仓</p>
              <p className="text-[10px] mt-1">添加持仓可获取相关事件推送</p>
            </div>
          )}
        </div>

        {/* Disclaimer */}
        <div className="px-4 py-6 text-center">
          <div className="flex items-center justify-center gap-1 text-[10px] text-gray-300 mb-1">
            <FileText className="w-3 h-3" />
            <span>免责声明</span>
          </div>
          <p className="text-[10px] text-gray-300 leading-relaxed px-4">
            本应用仅用于信息整理与展示，不构成任何投资建议。
            投资有风险，入市需谨慎。所有信息来源于公开渠道，
            不保证信息的准确性和完整性。
          </p>
        </div>
      </ScrollArea>

      {/* Add Holding Dialog */}
      <Dialog open={addHoldingOpen} onOpenChange={setAddHoldingOpen}>
        <DialogContent className="sm:max-w-[320px] rounded-2xl">
          <DialogHeader>
            <DialogTitle className="text-base">添加持仓</DialogTitle>
          </DialogHeader>
          <div className="py-2 space-y-3">
            <div>
              <label className="text-xs text-gray-500 mb-1 block">股票代码</label>
              <Input placeholder="如: 300750.SZ" value={newTicker} onChange={(e) => setNewTicker(e.target.value)} />
            </div>
            <div>
              <label className="text-xs text-gray-500 mb-1 block">股票名称</label>
              <Input placeholder="如: 宁德时代" value={newTickerName} onChange={(e) => setNewTickerName(e.target.value)} />
            </div>
            <Button
              className="w-full bg-blue-600 hover:bg-blue-700"
              onClick={handleAddHolding}
              disabled={createHolding.isPending || !newTicker.trim() || !newTickerName.trim()}
            >
              {createHolding.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : '添加'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Settings Dialog */}
      <Dialog open={settingsOpen} onOpenChange={setSettingsOpen}>
        <DialogContent className="sm:max-w-[320px] rounded-2xl">
          <DialogHeader>
            <DialogTitle className="text-base">风险偏好设置</DialogTitle>
          </DialogHeader>
          <div className="py-2 space-y-2">
            {riskLevels.map((level) => (
              <button
                key={level.key}
                onClick={() => {
                  handleUpdateRiskLevel(level.key);
                  setSettingsOpen(false);
                }}
                className={`w-full text-left p-3 rounded-xl border transition-colors ${
                  prefs?.riskLevel === level.key
                    ? 'border-blue-500 bg-blue-50'
                    : 'border-gray-100 hover:bg-gray-50'
                }`}
              >
                <div className="text-sm font-medium text-gray-900">{level.label}</div>
                <div className="text-xs text-gray-500 mt-0.5">{level.desc}</div>
              </button>
            ))}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
