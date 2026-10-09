import { useState } from 'react';
import { Routes, Route } from 'react-router';
import BottomNav from '@/components/BottomNav';
import DiscoverPage from '@/pages/DiscoverPage';
import AdvisorPage from '@/pages/AdvisorPage';
import ProfilePage from '@/pages/ProfilePage';
import Login from '@/pages/Login';
import NotFound from '@/pages/NotFound';
import type { TabType } from '@/types';

function MainLayout() {
  const [activeTab, setActiveTab] = useState<TabType>('advisor');

  return (
    <div className="h-screen w-full bg-gray-100 flex justify-center">
      <div className="w-full max-w-md h-full bg-white relative flex flex-col overflow-hidden shadow-2xl">
        {/* Main Content */}
        <div className="flex-1 overflow-hidden">
          {activeTab === 'discover' && <DiscoverPage />}
          {activeTab === 'advisor' && <AdvisorPage />}
          {activeTab === 'profile' && <ProfilePage />}
        </div>

        {/* Bottom Navigation */}
        <BottomNav activeTab={activeTab} onTabChange={setActiveTab} />
      </div>
    </div>
  );
}

function App() {
  return (
    <Routes>
      <Route path="/" element={<MainLayout />} />
      <Route path="/login" element={<Login />} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}

export default App;
