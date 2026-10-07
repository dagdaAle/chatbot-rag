import { lazy, Suspense, useEffect, useState, type ReactNode, type CSSProperties } from 'react';
import { useLocation } from 'react-router-dom';
import { ReaderContext } from '@/context/ReaderContext';
import type { PDFSelection } from '@/components/pdf/PDFReader';
import { Button } from '@/components/ui/button';
const PDFReader = lazy(() => import('@/components/pdf/PDFReader'));
import { Outlet } from 'react-router-dom';
import { SidebarInset, SidebarProvider, SidebarTrigger } from '@/components/ui/sidebar';
import { Separator } from '@/components/ui/separator';
import { AppSidebar } from './AppSidebar';

export function AppLayout() {
  const [selection, setSelection] = useState<PDFSelection | null>(null);
  const [collapsed, setCollapsed] = useState(false);
  const [mobileChat, setMobileChat] = useState(false);
  const [chatWidth, setChatWidth] = useState(45);
  const location = useLocation();
  // eslint-disable-next-line react-hooks/set-state-in-effect -- a route change closes the document from the previous conversation
  useEffect(() => { setSelection(null); setCollapsed(false); }, [location.pathname]);
  const close = () => { setSelection(null); setCollapsed(false); };
  return <ReaderContext.Provider value={{ open: value => { setSelection(value); setCollapsed(false); setMobileChat(false); }, close }}>
    <SidebarProvider className="h-svh">
      <AppSidebar />
      <SidebarInset className="min-h-0 min-w-0 overflow-hidden">
        {selection && <div className="bg-background flex shrink-0 items-center gap-2 border-b px-3 py-1">
          <Button variant="ghost" size="sm" className="hidden md:inline-flex" onClick={() => setCollapsed(v => !v)}>{collapsed ? 'Mostra chat' : 'Comprimi chat'}</Button>
          <Button variant="ghost" size="sm" className="md:hidden" onClick={() => setMobileChat(v => !v)}>{mobileChat ? "Mostra PDF" : "Mostra chat"}</Button>
          <span className="text-muted-foreground truncate text-xs">{selection.filename}</span>
          <Button variant="ghost" size="sm" className="ml-auto" onClick={close}>Chiudi PDF</Button>
        </div>}
        <div className="flex min-h-0 flex-1 overflow-hidden">
          <div className={`${selection ? (collapsed ? 'hidden' : mobileChat ? 'block' : 'hidden md:block') : 'block'} min-h-0 min-w-0 w-full md:w-[var(--chat-width)]`} style={{ '--chat-width': selection ? `${chatWidth}%` : '100%' } as CSSProperties}><Outlet /></div>
          {selection && <>
            {!collapsed && <div role="separator" aria-label="Larghezza chat" aria-orientation="vertical" aria-valuenow={chatWidth} aria-valuemin={25} aria-valuemax={65} tabIndex={0}
              className="bg-border hover:bg-primary hidden w-1 shrink-0 cursor-col-resize md:block"
              onKeyDown={e => { if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); setChatWidth(v => Math.max(25, Math.min(65, v + (e.key === 'ArrowRight' ? 5 : -5)))); } }}
              onPointerDown={e => { e.currentTarget.setPointerCapture(e.pointerId); }}
              onPointerMove={e => { if (e.currentTarget.hasPointerCapture(e.pointerId)) { const bounds = e.currentTarget.parentElement!.getBoundingClientRect(); setChatWidth(Math.max(25, Math.min(65, (e.clientX - bounds.left) / bounds.width * 100))); } }}
              onPointerUp={e => e.currentTarget.releasePointerCapture(e.pointerId)} />}
            <div className={`${mobileChat ? "hidden md:block" : "block"} min-h-0 min-w-0 flex-1`}><Suspense fallback={<p className="p-6">Apertura PDF…</p>}><PDFReader selection={selection} onClose={close} /></Suspense></div>
          </>}
        </div>
      </SidebarInset>
    </SidebarProvider>
  </ReaderContext.Provider>;
}

/** Barra in cima a ogni pagina: apri/chiudi sidebar, titolo, azioni a destra. */
export function PageHeader({ title, children }: { title?: ReactNode; children?: ReactNode }) {
  return (
    <header className="bg-background/80 sticky top-0 z-10 flex h-14 shrink-0 items-center gap-2 border-b px-3 backdrop-blur">
      <SidebarTrigger />
      <Separator orientation="vertical" className="mr-1 data-[orientation=vertical]:h-5" />
      {title && <h1 className="truncate text-sm font-medium">{title}</h1>}
      <div className="ml-auto flex min-w-0 items-center gap-2">{children}</div>
    </header>
  );
}
