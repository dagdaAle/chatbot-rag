import { lazy, Suspense } from 'react';
import { Route, Routes } from 'react-router-dom';
import { ThemeProvider } from 'next-themes';
import { Toaster } from '@/components/ui/sonner';
import { TooltipProvider } from '@/components/ui/tooltip';
import { AppProvider } from '@/context/AppContext';
import { AppLayout } from '@/components/layout/AppLayout';
import { ChatPage } from '@/components/chat/ChatPage';
import { KnowledgePage } from '@/components/knowledge/KnowledgePage';
import { SettingsPage } from '@/components/settings/SettingsPage';

// react-pdf pesa: lo carichiamo solo quando si apre una fonte.
const PDFViewerPage = lazy(() => import('@/components/PDFViewerPage'));

function App() {
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
      <TooltipProvider delayDuration={300}>
        <AppProvider>
          <Routes>
            <Route element={<AppLayout />}>
              <Route index element={<ChatPage />} />
              <Route path="c/:id" element={<ChatPage />} />
              <Route path="knowledge" element={<KnowledgePage />} />
              <Route path="settings" element={<SettingsPage />} />
            </Route>
            <Route
              path="/pdf-viewer"
              element={
                <Suspense fallback={null}>
                  <PDFViewerPage />
                </Suspense>
              }
            />
          </Routes>
        </AppProvider>
        <Toaster richColors position="top-center" />
      </TooltipProvider>
    </ThemeProvider>
  );
}

export default App;
