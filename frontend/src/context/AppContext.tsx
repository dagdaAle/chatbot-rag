import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import {
  fetchConversations,
  fetchKnowledges,
  type ConversationItem,
  type KnowledgeItem,
} from '@/api/client';

const KB_STORAGE_KEY = 'chatbot-rag:knowledge';

interface AppState {
  conversations: ConversationItem[];
  conversationsLoading: boolean;
  reloadConversations: () => Promise<void>;
  knowledges: KnowledgeItem[];
  reloadKnowledges: () => Promise<void>;
  selectedKnowledgeId: string | null;
  setSelectedKnowledgeId: (id: string | null) => void;
}

const AppContext = createContext<AppState | null>(null);

function readStoredKnowledge(): string | null {
  try {
    return localStorage.getItem(KB_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [conversations, setConversations] = useState<ConversationItem[]>([]);
  const [conversationsLoading, setConversationsLoading] = useState(true);
  const [knowledges, setKnowledges] = useState<KnowledgeItem[]>([]);
  const [storedKnowledgeId, setSelected] = useState<string | null>(readStoredKnowledge);

  const reloadConversations = useCallback(async () => {
    try {
      const data = await fetchConversations();
      setConversations(data.conversations);
    } catch {
      // La sidebar mostra la lista vuota: non blocchiamo la chat.
    } finally {
      setConversationsLoading(false);
    }
  }, []);

  const reloadKnowledges = useCallback(async () => {
    try {
      const data = await fetchKnowledges();
      setKnowledges(data.knowledges);
    } catch {
      setKnowledges([]);
    }
  }, []);

  const setSelectedKnowledgeId = useCallback((id: string | null) => {
    setSelected(id);
    try {
      if (id) localStorage.setItem(KB_STORAGE_KEY, id);
      else localStorage.removeItem(KB_STORAGE_KEY);
    } catch {
      // Storage non disponibile: la scelta vale solo per questa sessione.
    }
  }, []);

  useEffect(() => {
    // Caricamento iniziale da API esterna: lo stato si aggiorna a fetch concluso.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    reloadConversations();
    reloadKnowledges();
  }, [reloadConversations, reloadKnowledges]);

  // Se la knowledge salvata non esiste più, ripiega sulla prima disponibile.
  const selectedKnowledgeId = knowledges.some((k) => k.id === storedKnowledgeId)
    ? storedKnowledgeId
    : (knowledges[0]?.id ?? null);

  return (
    <AppContext.Provider
      value={{
        conversations,
        conversationsLoading,
        reloadConversations,
        knowledges,
        reloadKnowledges,
        selectedKnowledgeId,
        setSelectedKnowledgeId,
      }}
    >
      {children}
    </AppContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useApp(): AppState {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp va usato dentro AppProvider');
  return ctx;
}
