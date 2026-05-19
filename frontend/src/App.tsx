import { useState } from 'react';
import { Routes, Route } from 'react-router-dom';
import ChatInterface from './components/ChatInterface';
import KnowledgeBase from './components/KnowledgeBase';
import Settings from './components/Settings';
import PDFViewerPage from './components/PDFViewerPage';
import { AppView } from './types';

function MainApp() {
  const [currentView, setCurrentView] = useState<AppView>(AppView.CHAT);

  const navigateTo = (view: 'chat' | 'admin' | 'settings') => {
    if (view === 'chat') setCurrentView(AppView.CHAT);
    else if (view === 'admin') setCurrentView(AppView.ADMIN);
    else if (view === 'settings') setCurrentView(AppView.SETTINGS);
  };

  const toggleChatAdmin = () => {
    setCurrentView(prev => prev === AppView.CHAT ? AppView.ADMIN : AppView.CHAT);
  };

  return (
    <>
      {currentView === AppView.CHAT && (
        <ChatInterface onNavigate={toggleChatAdmin} onSettings={() => navigateTo('settings')} />
      )}
      {currentView === AppView.ADMIN && (
        <KnowledgeBase onNavigate={toggleChatAdmin} onSettings={() => navigateTo('settings')} />
      )}
      {currentView === AppView.SETTINGS && (
        <Settings onNavigate={navigateTo} />
      )}
    </>
  );
}

function App() {
  return (
    <Routes>
      <Route path="/" element={<MainApp />} />
      <Route path="/pdf-viewer" element={<PDFViewerPage />} />
    </Routes>
  );
}

export default App;
