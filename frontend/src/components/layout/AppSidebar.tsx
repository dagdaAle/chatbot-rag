import { supabase } from '@/auth/supabase';
import { useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import { useTheme } from 'next-themes';
import { toast } from 'sonner';
import {
  BookOpen,
  MessageSquare,
  Monitor,
  Moon,
  MoreHorizontal,
  Settings,
  Sparkles,
  SquarePen,
  Sun,
  Trash2,
} from 'lucide-react';
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSkeleton,
  SidebarRail,
} from '@/components/ui/sidebar';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { deleteConversation, type ConversationItem } from '@/api/client';
import { useApp } from '@/context/AppContext';
import { errorMessage, groupByRecency } from '@/lib/format';

const NAV = [
  { to: '/knowledge', label: 'Knowledge base', icon: BookOpen },
  { to: '/settings', label: 'Impostazioni', icon: Settings },
];

const THEMES = [
  { value: 'light', label: 'Chiaro', icon: Sun },
  { value: 'dark', label: 'Scuro', icon: Moon },
  { value: 'system', label: 'Sistema', icon: Monitor },
];

export function AppSidebar() {
  const { conversations, conversationsLoading, reloadConversations } = useApp();
  const { id: currentId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const { theme, setTheme } = useTheme();
  const [toDelete, setToDelete] = useState<ConversationItem | null>(null);

  const confirmDelete = async () => {
    if (!toDelete) return;
    try {
      await deleteConversation(toDelete.id);
      if (toDelete.id === currentId) navigate('/');
      await reloadConversations();
      toast.success('Conversazione eliminata');
    } catch (err) {
      toast.error(errorMessage(err, 'Eliminazione non riuscita'));
    } finally {
      setToDelete(null);
    }
  };

  const ThemeIcon = THEMES.find((t) => t.value === theme)?.icon ?? Monitor;

  return (
    <Sidebar collapsible="offcanvas">
      <SidebarHeader>
        <div className="flex items-center gap-2 px-2 py-1.5">
          <div className="bg-primary text-primary-foreground flex size-8 items-center justify-center rounded-lg">
            <Sparkles className="size-4" />
          </div>
          <div className="grid leading-tight">
            <span className="text-sm font-semibold">Chatbot RAG</span>
            <span className="text-muted-foreground text-xs">Chiedi ai tuoi documenti</span>
          </div>
        </div>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton asChild isActive={location.pathname === '/'}>
              <Link to="/">
                <SquarePen />
                <span>Nuova chat</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
          {NAV.map(({ to, label, icon: Icon }) => (
            <SidebarMenuItem key={to}>
              <SidebarMenuButton asChild isActive={location.pathname.startsWith(to)}>
                <Link to={to}>
                  <Icon />
                  <span>{label}</span>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          ))}
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        {conversationsLoading ? (
          <SidebarGroup>
            <SidebarGroupLabel>Conversazioni</SidebarGroupLabel>
            <SidebarMenu>
              {Array.from({ length: 5 }).map((_, i) => (
                <SidebarMenuItem key={i}>
                  <SidebarMenuSkeleton />
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroup>
        ) : conversations.length === 0 ? (
          <p className="text-muted-foreground px-4 py-6 text-center text-xs">
            Nessuna conversazione. Le chat compaiono qui dopo la prima domanda.
          </p>
        ) : (
          groupByRecency(conversations).map((group) => (
            <SidebarGroup key={group.label}>
              <SidebarGroupLabel>{group.label}</SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu>
                  {group.items.map((conv) => (
                    <SidebarMenuItem key={conv.id}>
                      <SidebarMenuButton asChild isActive={conv.id === currentId}>
                        <Link to={`/c/${conv.id}`} title={conv.title}>
                          <MessageSquare />
                          <span>{conv.title}</span>
                        </Link>
                      </SidebarMenuButton>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <SidebarMenuAction showOnHover aria-label="Azioni conversazione">
                            <MoreHorizontal />
                          </SidebarMenuAction>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent side="right" align="start">
                          <DropdownMenuItem variant="destructive" onSelect={() => setToDelete(conv)}>
                            <Trash2 />
                            Elimina
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </SidebarMenuItem>
                  ))}
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>
          ))
        )}
      </SidebarContent>

      <SidebarFooter>
        <SidebarMenuButton onClick={async () => {
          const { error } = await supabase.auth.signOut({ scope: 'local' });
          if (error) toast.error('Uscita non riuscita');
        }}>Esci</SidebarMenuButton>
        <SidebarMenu>
          <SidebarMenuItem>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <SidebarMenuButton>
                  <ThemeIcon />
                  <span>Tema</span>
                </SidebarMenuButton>
              </DropdownMenuTrigger>
              <DropdownMenuContent side="top" align="start">
                {THEMES.map(({ value, label, icon: Icon }) => (
                  <DropdownMenuItem key={value} onSelect={() => setTheme(value)}>
                    <Icon />
                    {label}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
      <SidebarRail />

      <AlertDialog open={toDelete !== null} onOpenChange={(open) => !open && setToDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Eliminare la conversazione?</AlertDialogTitle>
            <AlertDialogDescription>
              «{toDelete?.title}» e tutti i suoi messaggi verranno cancellati definitivamente.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Annulla</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={confirmDelete}>
              Elimina
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Sidebar>
  );
}
