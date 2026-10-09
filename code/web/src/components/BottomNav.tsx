import { Compass, MessageCircle, User } from 'lucide-react';
import type { TabType } from '@/types';

interface Props {
  activeTab: TabType;
  onTabChange: (tab: TabType) => void;
}

const tabs: { key: TabType; label: string; icon: React.ReactNode }[] = [
  { key: 'discover', label: '发现', icon: <Compass className="w-5 h-5" /> },
  { key: 'advisor', label: '参谋', icon: <MessageCircle className="w-5 h-5" /> },
  { key: 'profile', label: '我的', icon: <User className="w-5 h-5" /> },
];

export default function BottomNav({ activeTab, onTabChange }: Props) {
  return (
    <nav className="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-100 z-50 safe-area-bottom">
      <div className="flex items-center justify-around h-14 max-w-md mx-auto">
        {tabs.map(tab => {
          const isActive = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              onClick={() => onTabChange(tab.key)}
              className={`flex flex-col items-center justify-center w-full h-full gap-0.5 transition-colors ${
                isActive ? 'text-blue-600' : 'text-gray-400'
              }`}
            >
              {tab.icon}
              <span className="text-[10px] font-medium">{tab.label}</span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}
