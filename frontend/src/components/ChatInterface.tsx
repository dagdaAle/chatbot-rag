import { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import {
  sendChatMessage,
  fetchChatModels,
  setChatModel,
  fetchKnowledges,
  getPDFViewerUrl,
  fetchConversations,
  fetchConversation,
  deleteConversation,
  type ChatSource,
  type ChatMessageItem,
  type ModelInfo,
  type KnowledgeItem,
  type ConversationItem,
} from '../api/client';

interface ChatInterfaceProps {
  onNavigate: () => void;
  onSettings: () => void;
}

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: ChatSource[];
  timestamp: Date;
}

/* ────────────────────────────────────────────────────────── */
/*  Source Preview Component                                  */
/* ────────────────────────────────────────────────────────── */
const SourcePreview: React.FC<{
  source: ChatSource;
  knowledgeId: string | null;
  onClose: () => void;
}> = ({ source, knowledgeId, onClose }) => {
  const pageLabel =
    source.page_start === source.page_end
      ? `Pagina ${source.page_start}`
      : `Pagine ${source.page_start}-${source.page_end}`;

  const handleOpenPdfViewer = () => {
    if (!knowledgeId || !source.document_id) return;
    const viewerUrl = getPDFViewerUrl({
      knowledgeId,
      documentId: source.document_id,
      pageStart: source.page_start,
      pageEnd: source.page_end,
      text: source.text,
      filename: source.filename,
      score: source.score,
    });
    window.open(viewerUrl, '_blank');
  };

  const canOpenPdf = !!knowledgeId && !!source.document_id && source.page_start > 0;

  return (
    <div className="mt-2 bg-white border border-[#cee2e9] rounded-xl shadow-md overflow-hidden animate-in fade-in duration-200">
      <div className="flex items-center justify-between px-4 py-3 bg-gray-50 border-b border-[#cee2e9]">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="material-symbols-outlined text-admin-primary text-[18px]">description</span>
          <span className="text-sm font-semibold text-[#0d181c]">{source.filename}</span>
          <span className="text-xs text-chat-text-muted bg-[#e7f0f3] px-2 py-0.5 rounded-full">
            Chunk #{source.chunk_index + 1}
          </span>
          <span className="text-xs text-chat-text-muted bg-amber-50 text-amber-700 px-2 py-0.5 rounded-full">
            {pageLabel}
          </span>
          <span className="text-xs text-chat-text-muted">
            Rilevanza: {(source.score * 100).toFixed(0)}%
          </span>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {canOpenPdf && (
            <button
              onClick={handleOpenPdfViewer}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-amber-50 border border-amber-200 text-amber-700 text-xs font-semibold hover:bg-amber-100 transition-colors"
              title={`Apri PDF a ${pageLabel.toLowerCase()}`}
            >
              <span className="material-symbols-outlined text-[16px]">picture_as_pdf</span>
              Apri nel Viewer
            </button>
          )}
          <button
            onClick={onClose}
            className="p-1 rounded-md hover:bg-gray-200 transition-colors"
          >
            <span className="material-symbols-outlined text-[18px] text-chat-text-muted">close</span>
          </button>
        </div>
      </div>
      <div className="px-4 py-4 max-h-64 overflow-y-auto">
        <p className="text-sm text-[#0d181c] leading-relaxed whitespace-pre-wrap font-mono bg-[#f8fbfc] p-3 rounded-lg border border-[#e7f0f3]">
          {source.text}
        </p>
      </div>
    </div>
  );
};

/* ────────────────────────────────────────────────────────── */
/*  Main Chat Component                                       */
/* ────────────────────────────────────────────────────────── */
const ChatInterface: React.FC<ChatInterfaceProps> = ({ onNavigate, onSettings }) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Model selector state
  const [chatModels, setChatModels] = useState<ModelInfo[]>([]);
  const [currentModel, setCurrentModel] = useState('');
  const [currentProvider, setCurrentProvider] = useState('');
  const [showModelSelector, setShowModelSelector] = useState(false);
  const [modelLoading, setModelLoading] = useState(false);
  const modelSelectorRef = useRef<HTMLDivElement>(null);

  // Knowledge selector state
  const [knowledges, setKnowledges] = useState<KnowledgeItem[]>([]);
  const [selectedKnowledgeId, setSelectedKnowledgeId] = useState<string | null>(null);
  const [showKBSelector, setShowKBSelector] = useState(false);
  const kbSelectorRef = useRef<HTMLDivElement>(null);

  // Source preview state
  const [expandedSource, setExpandedSource] = useState<{ messageId: string; sourceIdx: number } | null>(null);

  // Conversations state
  const [conversations, setConversations] = useState<ConversationItem[]>([]);
  const [currentConversationId, setCurrentConversationId] = useState<string | null>(null);
  const [loadingConversations, setLoadingConversations] = useState(false);
  const [loadingChat, setLoadingChat] = useState(false);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, expandedSource]);

  // Carica modelli, knowledge e conversazioni
  useEffect(() => {
    fetchChatModels()
      .then((data) => {
        setChatModels(data.models);
        setCurrentModel(data.current);
        setCurrentProvider(data.provider);
      })
      .catch(console.error);

    fetchKnowledges()
      .then((data) => {
        setKnowledges(data.knowledges);
        // Seleziona la prima knowledge se esiste
        if (data.knowledges.length > 0) {
          setSelectedKnowledgeId(data.knowledges[0].id);
        }
      })
      .catch(console.error);

    // Carica conversazioni
    loadConversations();
  }, []);

  const loadConversations = async () => {
    setLoadingConversations(true);
    try {
      const data = await fetchConversations();
      setConversations(data.conversations);
    } catch (err) {
      console.error('Errore caricamento conversazioni:', err);
    } finally {
      setLoadingConversations(false);
    }
  };

  // Chiudi dropdown al click fuori
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (modelSelectorRef.current && !modelSelectorRef.current.contains(e.target as Node)) {
        setShowModelSelector(false);
      }
      if (kbSelectorRef.current && !kbSelectorRef.current.contains(e.target as Node)) {
        setShowKBSelector(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleModelChange = async (model: ModelInfo) => {
    setModelLoading(true);
    try {
      await setChatModel(model.id, model.provider);
      setCurrentModel(model.id);
      setCurrentProvider(model.provider);
      setShowModelSelector(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Errore cambio modello');
    } finally {
      setModelLoading(false);
    }
  };

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = '44px';
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 128) + 'px';
    }
  }, [input]);

  const handleSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!input.trim() || loading) return;

    const question = input.trim();
    setInput('');
    setError(null);
    setExpandedSource(null);

    const userMessage: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: question,
      timestamp: new Date(),
    };

    const conversationHistory: ChatMessageItem[] = messages.map((msg) => ({
      role: msg.role,
      content: msg.content,
    }));

    setMessages((prev) => [...prev, userMessage]);
    setLoading(true);

    try {
      const response = await sendChatMessage(
        question,
        conversationHistory,
        5,
        selectedKnowledgeId || undefined,
        currentConversationId || undefined,
      );
      
      // Aggiorna conversation_id e ricarica lista
      if (response.conversation_id) {
        if (!currentConversationId) {
          setCurrentConversationId(response.conversation_id);
        }
        // Ricarica sempre la lista (per aggiornare updated_at e nuove conversazioni)
        loadConversations();
      }

      const assistantMessage: Message = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: response.answer,
        sources: response.sources,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, assistantMessage]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Errore durante la chat');
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const formatTime = (date: Date) => {
    return date.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
  };

  const clearChat = async () => {
    setMessages([]);
    setError(null);
    setExpandedSource(null);
    setCurrentConversationId(null);
  };

  const handleNewChat = async () => {
    await clearChat();
    // Non creiamo subito una conversazione, verrà creata al primo messaggio
  };

  const handleLoadConversation = async (conversationId: string) => {
    // Evita ricaricare la stessa conversazione
    if (conversationId === currentConversationId) return;
    
    try {
      setLoadingChat(true);
      const conv = await fetchConversation(conversationId);
      
      // Converti i messaggi dal formato API al formato Message
      const loadedMessages: Message[] = conv.messages.map((msg) => ({
        id: msg.id,
        role: msg.role as 'user' | 'assistant',
        content: msg.content,
        sources: msg.sources as ChatSource[] || undefined,
        timestamp: msg.timestamp ? new Date(msg.timestamp) : new Date(),
      }));

      setMessages(loadedMessages);
      setCurrentConversationId(conversationId);
      setError(null);
      setExpandedSource(null);
      
      // Ripristina la knowledge_id associata alla conversazione
      if (conv.knowledge_id) {
        setSelectedKnowledgeId(conv.knowledge_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Errore caricamento conversazione');
    } finally {
      setLoadingChat(false);
    }
  };

  const handleDeleteConversation = async (conversationId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!window.confirm('Sei sicuro di voler eliminare questa conversazione?')) {
      return;
    }

    try {
      await deleteConversation(conversationId);
      
      // Se era la conversazione corrente, resetta
      if (conversationId === currentConversationId) {
        setMessages([]);
        setCurrentConversationId(null);
      }
      
      // Ricarica la lista
      loadConversations();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Errore eliminazione conversazione');
    }
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffDays === 0) {
      return 'Oggi';
    } else if (diffDays === 1) {
      return 'Ieri';
    } else if (diffDays < 7) {
      return `${diffDays} giorni fa`;
    } else {
      return date.toLocaleDateString('it-IT', { day: 'numeric', month: 'short' });
    }
  };

  const toggleSourcePreview = (messageId: string, sourceIdx: number) => {
    if (expandedSource?.messageId === messageId && expandedSource?.sourceIdx === sourceIdx) {
      setExpandedSource(null);
    } else {
      setExpandedSource({ messageId, sourceIdx });
    }
  };

  const selectedKB = knowledges.find((kb) => kb.id === selectedKnowledgeId);

  return (
    <div className="flex h-full w-full bg-chat-bg font-display">
      {/* Sidebar */}
      <aside className="w-[280px] bg-chat-sidebar border-r border-[#e7f0f3] flex flex-col justify-between shrink-0 h-full z-20 hidden md:flex">
        <div className="flex flex-col h-full p-4">
          {/* Brand */}
          <div className="flex flex-col mb-8 px-2">
            <h1 className="text-[#0d181b] text-xl font-bold tracking-tight">Intecha</h1>
            <p className="text-chat-text-muted text-sm font-normal">Professional AI Suite</p>
          </div>

          {/* New Chat Button */}
          <button
            onClick={handleNewChat}
            className="flex w-full items-center justify-center gap-2 rounded-lg h-11 px-4 bg-chat-primary hover:bg-opacity-90 transition-colors text-[#0d181b] text-sm font-bold tracking-wide shadow-sm mb-6"
          >
            <span className="material-symbols-outlined text-lg">add</span>
            <span>Nuova Chat</span>
          </button>

          {/* Chat History */}
          <div className="flex flex-col gap-2 overflow-y-auto flex-1 scrollbar-hide">
            {loadingConversations ? (
              <div className="px-3 py-4 text-center text-sm text-chat-text-muted">
                Caricamento...
              </div>
            ) : conversations.length === 0 ? (
              <div className="px-3 py-4 text-center text-sm text-chat-text-muted">
                Nessuna conversazione
              </div>
            ) : (
              <>
                <h3 className="px-3 text-xs font-semibold text-chat-text-muted uppercase tracking-wider">Conversazioni</h3>
                <div className="flex flex-col gap-1">
                  {conversations.map((conv) => (
                    <button
                      key={conv.id}
                      onClick={() => handleLoadConversation(conv.id)}
                      className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors group relative ${
                        conv.id === currentConversationId
                          ? 'bg-[#e7f0f3]'
                          : 'hover:bg-[#e7f0f3]/50'
                      }`}
                    >
                      <span className="material-symbols-outlined text-[#0d181b] text-[20px] shrink-0">
                        chat_bubble
                      </span>
                      <div className="flex-1 min-w-0 text-left">
                        <p className="text-[#0d181b] text-sm font-medium truncate">
                          {conv.title}
                        </p>
                        <p className="text-xs text-chat-text-muted">
                          {formatDate(conv.updated_at)}
                        </p>
                      </div>
                      <button
                        onClick={(e) => handleDeleteConversation(conv.id, e)}
                        className="opacity-0 group-hover:opacity-100 p-1 rounded-md hover:bg-red-100 transition-all shrink-0"
                        title="Elimina conversazione"
                      >
                        <span className="material-symbols-outlined text-[16px] text-red-600">delete</span>
                      </button>
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>

          {/* Footer Menu */}
          <div className="flex flex-col gap-1 pt-4 border-t border-[#e7f0f3] mt-2">
            <button onClick={onNavigate} className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-[#e7f0f3] transition-colors w-full text-left">
              <span className="material-symbols-outlined text-[#0d181b] text-[22px]">folder</span>
              <span className="text-[#0d181b] text-sm font-medium">Gestione Documenti</span>
            </button>
            <button onClick={onSettings} className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-[#e7f0f3] transition-colors w-full text-left">
              <span className="material-symbols-outlined text-[#0d181b] text-[22px]">settings</span>
              <span className="text-[#0d181b] text-sm font-medium">Impostazioni</span>
            </button>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col h-full relative bg-white">
        {/* Top Navbar */}
        <header className="flex items-center justify-between px-6 py-4 border-b border-[#e7f0f3] bg-white/80 backdrop-blur-sm z-10 sticky top-0">
          <div className="flex items-center gap-3">
            <div className="md:hidden p-1 mr-1 rounded-md hover:bg-slate-100 cursor-pointer">
              <span className="material-symbols-outlined text-[#0d181b]">menu</span>
            </div>
            <div className="flex items-center justify-center size-8 rounded-lg bg-chat-primary/10 text-chat-primary">
              <span className="material-symbols-filled text-[24px]">smart_toy</span>
            </div>
            <div className="flex flex-col">
              <div className="flex items-center gap-2">
                <h2 className="text-[#0d181b] text-base font-bold leading-tight">Intecha AI</h2>
                <span className="flex size-2 rounded-full bg-emerald-500"></span>
              </div>
              <p className="text-xs text-chat-text-muted">RAG Assistant • Pronto</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {/* Knowledge Selector */}
            <div className="relative" ref={kbSelectorRef}>
              <button
                onClick={() => setShowKBSelector(!showKBSelector)}
                className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-[#e7f0f3] hover:bg-[#e7f0f3] text-sm transition-colors"
                title="Seleziona Knowledge Base"
              >
                <span className="material-symbols-outlined text-[18px] text-chat-text-muted">auto_stories</span>
                <span className="text-[#0d181b] font-medium max-w-[140px] truncate hidden sm:inline">
                  {selectedKB ? selectedKB.name : 'Tutte'}
                </span>
                <span className="material-symbols-outlined text-[16px] text-chat-text-muted">expand_more</span>
              </button>

              {showKBSelector && (
                <div className="absolute right-0 top-full mt-2 w-72 bg-white rounded-xl border border-[#e7f0f3] shadow-lg z-50 overflow-hidden">
                  <div className="px-4 py-3 border-b border-[#e7f0f3] bg-gray-50/50">
                    <p className="text-xs font-semibold text-chat-text-muted uppercase tracking-wider">Knowledge Base</p>
                  </div>
                  <div className="max-h-64 overflow-y-auto">
                    {/* Opzione "Nessuna" per ricerca globale legacy */}
                    <button
                      onClick={() => { setSelectedKnowledgeId(null); setShowKBSelector(false); }}
                      className={`w-full flex items-center gap-3 px-4 py-3 hover:bg-[#e7f0f3] transition-colors text-left ${!selectedKnowledgeId ? 'bg-chat-primary/10' : ''}`}
                    >
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-[#0d181b]">Nessuna (Legacy)</p>
                        <p className="text-xs text-chat-text-muted">Cerca nella collezione globale</p>
                      </div>
                      {!selectedKnowledgeId && (
                        <span className="material-symbols-outlined text-chat-primary text-[18px] shrink-0">check</span>
                      )}
                    </button>
                    {knowledges.map((kb) => (
                      <button
                        key={kb.id}
                        onClick={() => { setSelectedKnowledgeId(kb.id); setShowKBSelector(false); }}
                        className={`w-full flex items-center gap-3 px-4 py-3 hover:bg-[#e7f0f3] transition-colors text-left ${kb.id === selectedKnowledgeId ? 'bg-chat-primary/10' : ''}`}
                      >
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-[#0d181b] truncate">{kb.name}</p>
                          <p className="text-xs text-chat-text-muted">{kb.documents_count} documenti</p>
                        </div>
                        {kb.id === selectedKnowledgeId && (
                          <span className="material-symbols-outlined text-chat-primary text-[18px] shrink-0">check</span>
                        )}
                      </button>
                    ))}
                    {knowledges.length === 0 && (
                      <div className="px-4 py-6 text-center text-sm text-chat-text-muted">
                        Nessuna knowledge creata
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* Model Selector */}
            <div className="relative" ref={modelSelectorRef}>
              <button
                onClick={() => setShowModelSelector(!showModelSelector)}
                disabled={modelLoading}
                className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-[#e7f0f3] hover:bg-[#e7f0f3] text-sm transition-colors"
                title="Seleziona modello"
              >
                <span className="material-symbols-outlined text-[18px] text-chat-text-muted">model_training</span>
                <span className="text-[#0d181b] font-medium max-w-[140px] truncate hidden sm:inline">
                  {currentModel || 'Seleziona modello'}
                </span>
                <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${currentProvider === 'ollama' ? 'bg-purple-100 text-purple-700' : 'bg-emerald-100 text-emerald-700'}`}>
                  {currentProvider || '...'}
                </span>
                <span className="material-symbols-outlined text-[16px] text-chat-text-muted">expand_more</span>
              </button>

              {showModelSelector && (
                <div className="absolute right-0 top-full mt-2 w-72 bg-white rounded-xl border border-[#e7f0f3] shadow-lg z-50 overflow-hidden">
                  <div className="px-4 py-3 border-b border-[#e7f0f3] bg-gray-50/50">
                    <p className="text-xs font-semibold text-chat-text-muted uppercase tracking-wider">Modello Chat</p>
                  </div>
                  <div className="max-h-64 overflow-y-auto">
                    {chatModels.length === 0 ? (
                      <div className="px-4 py-6 text-center text-sm text-chat-text-muted">
                        Nessun modello disponibile
                      </div>
                    ) : (
                      chatModels.map((model) => (
                        <button
                          key={`${model.provider}-${model.id}`}
                          onClick={() => handleModelChange(model)}
                          className={`w-full flex items-center gap-3 px-4 py-3 hover:bg-[#e7f0f3] transition-colors text-left ${
                            model.id === currentModel && model.provider === currentProvider ? 'bg-chat-primary/10' : ''
                          }`}
                        >
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-[#0d181b] truncate">{model.name}</p>
                            <p className="text-xs text-chat-text-muted truncate">{model.id}</p>
                          </div>
                          <span className={`shrink-0 px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                            model.provider === 'ollama' ? 'bg-purple-100 text-purple-700' : 'bg-emerald-100 text-emerald-700'
                          }`}>
                            {model.provider}
                          </span>
                          {model.id === currentModel && model.provider === currentProvider && (
                            <span className="material-symbols-outlined text-chat-primary text-[18px] shrink-0">check</span>
                          )}
                        </button>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>

            <button
              onClick={onNavigate}
              className="md:hidden flex items-center justify-center size-9 rounded-lg hover:bg-[#e7f0f3] text-chat-text-muted transition-colors"
              title="Gestione Documenti"
            >
              <span className="material-symbols-outlined text-[20px]">folder</span>
            </button>
            <button
              onClick={handleNewChat}
              className="flex items-center justify-center size-9 rounded-lg hover:bg-[#e7f0f3] text-chat-text-muted transition-colors"
              title="Nuova Chat"
            >
              <span className="material-symbols-outlined text-[20px]">add</span>
            </button>
          </div>
        </header>

        {/* Chat Area */}
        <div className="flex-1 overflow-y-auto p-4 md:px-20 lg:px-40 pb-32">
          <div className="max-w-3xl mx-auto flex flex-col gap-6 py-6">

            {/* Welcome message when empty */}
            {messages.length === 0 && (
              <div className="flex flex-col items-center justify-center h-full min-h-[400px] text-center">
                <div className="flex items-center justify-center size-16 rounded-2xl bg-chat-primary/10 text-chat-primary mb-6">
                  <span className="material-symbols-filled text-[40px]">smart_toy</span>
                </div>
                <h3 className="text-xl font-bold text-[#0d181b] mb-2">Come posso aiutarti?</h3>
                <p className="text-chat-text-muted max-w-md">
                  Fai una domanda sui documenti caricati nella Knowledge Base.
                  Utilizzo la tecnologia RAG per trovare informazioni rilevanti.
                </p>
                {selectedKB && (
                  <div className="mt-3 flex items-center gap-2 px-3 py-1.5 rounded-full bg-[#e7f0f3]">
                    <span className="material-symbols-outlined text-[16px] text-chat-text-muted">auto_stories</span>
                    <span className="text-sm text-[#0d181b] font-medium">{selectedKB.name}</span>
                    <span className="text-xs text-chat-text-muted">({selectedKB.documents_count} documenti)</span>
                  </div>
                )}
                <div className="mt-6 flex flex-wrap gap-2 justify-center">
                  <button
                    onClick={() => setInput('Quali documenti sono disponibili?')}
                    className="px-4 py-2 rounded-lg border border-[#e7f0f3] text-sm text-chat-text-muted hover:bg-[#e7f0f3] transition-colors"
                  >
                    Quali documenti sono disponibili?
                  </button>
                  <button
                    onClick={() => setInput('Riassumi il contenuto principale')}
                    className="px-4 py-2 rounded-lg border border-[#e7f0f3] text-sm text-chat-text-muted hover:bg-[#e7f0f3] transition-colors"
                  >
                    Riassumi il contenuto principale
                  </button>
                </div>
              </div>
            )}

            {/* Messages */}
            {messages.map((msg, index) => (
              <div key={msg.id}>
                {/* Date divider for first message */}
                {index === 0 && (
                  <div className="flex justify-center mb-6">
                    <span className="text-xs font-medium text-chat-text-muted bg-[#f8fbfc] px-3 py-1 rounded-full">
                      Oggi, {formatTime(msg.timestamp)}
                    </span>
                  </div>
                )}

                {msg.role === 'assistant' ? (
                  /* AI Message */
                  <div className="flex items-end gap-4 mb-6">
                    <div className="flex items-center justify-center size-8 rounded-full bg-chat-primary/20 shrink-0">
                      <span className="material-symbols-filled text-chat-primary text-[18px]">smart_toy</span>
                    </div>
                    <div className="flex flex-col gap-1 max-w-[85%] md:max-w-[75%]">
                      <div className="flex items-center gap-2 ml-1">
                        <span className="text-xs font-semibold text-[#0d181b]">Intecha AI</span>
                        <span className="text-xs text-chat-text-muted">{formatTime(msg.timestamp)}</span>
                      </div>
                      <div className="p-4 rounded-2xl rounded-bl-none bg-chat-bubble-ai text-[#0d181b] text-[15px] shadow-sm markdown-content">
                        <ReactMarkdown>{msg.content}</ReactMarkdown>
                      </div>

                      {/* Sources - Cliccabili */}
                      {msg.sources && msg.sources.length > 0 && (
                        <div className="flex flex-col gap-1 mt-2 ml-1">
                          <span className="text-xs text-chat-text-muted mb-1">Fonti (clicca per vedere il contenuto):</span>
                          <div className="flex flex-wrap gap-2">
                            {msg.sources.map((src, i) => {
                              const isExpanded = expandedSource?.messageId === msg.id && expandedSource?.sourceIdx === i;
                              return (
                                <button
                                  key={i}
                                  onClick={() => toggleSourcePreview(msg.id, i)}
                                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all flex items-center gap-1.5 ${
                                    isExpanded
                                      ? 'bg-admin-primary/20 text-admin-primary border border-admin-primary/30 shadow-sm'
                                      : 'bg-[#e7f0f3] text-[#0d181b] hover:bg-[#d5e5ea] border border-transparent'
                                  }`}
                                  title={`Rilevanza: ${(src.score * 100).toFixed(0)}% · Pag. ${src.page_start}${src.page_end !== src.page_start ? `-${src.page_end}` : ''}`}
                                >
                                  <span className="material-symbols-outlined text-[14px]">
                                    {isExpanded ? 'visibility' : 'description'}
                                  </span>
                                  {src.filename}
                                  <span className="text-[10px] opacity-70">p.{src.page_start}</span>
                                </button>
                              );
                            })}
                          </div>

                          {/* Expanded source preview */}
                          {expandedSource?.messageId === msg.id && msg.sources[expandedSource.sourceIdx] && (
                            <SourcePreview
                              source={msg.sources[expandedSource.sourceIdx]}
                              knowledgeId={selectedKnowledgeId}
                              onClose={() => setExpandedSource(null)}
                            />
                          )}
                        </div>
                      )}

                      <div className="flex gap-2 mt-1">
                        <button
                          onClick={() => navigator.clipboard.writeText(msg.content)}
                          className="px-3 py-1.5 rounded-full border border-slate-200 text-xs font-medium text-chat-text-muted hover:bg-slate-50 transition-colors flex items-center gap-1"
                        >
                          <span className="material-symbols-outlined text-[16px]">content_copy</span> Copia
                        </button>
                      </div>
                    </div>
                  </div>
                ) : (
                  /* User Message */
                  <div className="flex items-end gap-4 justify-end mb-6">
                    <div className="flex flex-col gap-1 items-end max-w-[85%] md:max-w-[75%]">
                      <div className="flex items-center gap-2 mr-1">
                        <span className="text-xs text-chat-text-muted">{formatTime(msg.timestamp)}</span>
                        <span className="text-xs font-semibold text-[#0d181b]">Tu</span>
                      </div>
                      <div className="p-4 rounded-2xl rounded-br-none bg-chat-primary text-[#0d181b] text-[15px] leading-relaxed shadow-md">
                        <p>{msg.content}</p>
                      </div>
                    </div>
                    <div className="flex items-center justify-center size-8 rounded-full bg-slate-200 shrink-0">
                      <span className="material-symbols-outlined text-slate-600 text-[18px]">person</span>
                    </div>
                  </div>
                )}
              </div>
            ))}

            {/* Loading chat indicator (caricamento conversazione) */}
            {loadingChat && (
              <div className="flex justify-center py-8">
                <div className="flex items-center gap-2 text-chat-text-muted text-sm">
                  <span className="material-symbols-outlined animate-spin text-[20px]">progress_activity</span>
                  Caricamento conversazione...
                </div>
              </div>
            )}

            {/* Typing indicator (generazione risposta) */}
            {loading && (
              <div className="flex items-end gap-4 mb-6">
                <div className="flex items-center justify-center size-8 rounded-full bg-chat-primary/20 shrink-0">
                  <span className="material-symbols-filled text-chat-primary text-[18px]">smart_toy</span>
                </div>
                <div className="p-4 rounded-2xl rounded-bl-none bg-chat-bubble-ai shadow-sm">
                  <div className="flex gap-1">
                    <span className="size-2 rounded-full bg-chat-text-muted animate-bounce" style={{ animationDelay: '0ms' }}></span>
                    <span className="size-2 rounded-full bg-chat-text-muted animate-bounce" style={{ animationDelay: '150ms' }}></span>
                    <span className="size-2 rounded-full bg-chat-text-muted animate-bounce" style={{ animationDelay: '300ms' }}></span>
                  </div>
                </div>
              </div>
            )}

            {/* Error message */}
            {error && (
              <div className="flex justify-center mb-6">
                <div className="px-4 py-2 rounded-lg bg-red-50 border border-red-200 text-red-600 text-sm">
                  {error}
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Input Area (Sticky Footer) */}
        <div className="w-full absolute bottom-0 bg-white pb-6 pt-2 px-4">
          <div className="max-w-3xl mx-auto">
            <form onSubmit={handleSubmit}>
              <div className="relative flex items-end gap-2 p-2 rounded-xl border border-[#e7f0f3] bg-white shadow-soft focus-within:ring-2 focus-within:ring-chat-primary/20 focus-within:border-chat-primary transition-all">
                <textarea
                  ref={textareaRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  className="w-full max-h-32 bg-transparent border-none focus:ring-0 focus:outline-none text-[#0d181b] placeholder:text-slate-400 py-2.5 px-2 resize-none text-[15px]"
                  placeholder={selectedKB ? `Cerca in "${selectedKB.name}"...` : 'Scrivi un messaggio...'}
                  rows={1}
                  style={{ minHeight: '44px' }}
                  disabled={loading}
                />
                <div className="flex items-center gap-1 shrink-0 pb-1">
                  <button
                    type="submit"
                    disabled={!input.trim() || loading}
                    className="p-2 bg-chat-primary text-[#0d181b] rounded-lg hover:brightness-95 transition-all shadow-sm flex items-center justify-center disabled:opacity-50 disabled:cursor-not-allowed"
                    title="Invia"
                  >
                    <span className="material-symbols-filled text-[20px]">arrow_upward</span>
                  </button>
                </div>
              </div>
            </form>
            <div className="text-center mt-3">
              <p className="text-[11px] text-chat-text-muted">Intecha può commettere errori. Considera di verificare le informazioni importanti.</p>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};

export default ChatInterface;
