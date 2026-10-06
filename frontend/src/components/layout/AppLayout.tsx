import type { ReactNode } from 'react';
import { Outlet } from 'react-router-dom';
import { SidebarInset, SidebarProvider, SidebarTrigger } from '@/components/ui/sidebar';
import { Separator } from '@/components/ui/separator';
import { AppSidebar } from './AppSidebar';

export function AppLayout() {
  return (
    <SidebarProvider className="h-svh">
      <AppSidebar />
      <SidebarInset className="min-h-0 overflow-hidden">
        <Outlet />
      </SidebarInset>
    </SidebarProvider>
  );
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
