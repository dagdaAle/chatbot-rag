import { useAuthUser } from '@/auth/AuthContext';
import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { ArrowUp, BookOpen, Cpu, Square } from 'lucide-react';
import { ChatContainerContent, ChatContainerRoot } from '@/components/ui/chat-container';
import {
  PromptInput,
  PromptInputAction,
  PromptInputActions,
  PromptInputTextarea,
} from '@/components/ui/prompt-input';
import { PromptSuggestion } from '@/components/ui/prompt-suggestion';
import { ScrollButton } from '@/components/ui/scroll-button';
import { Loader } from '@/components/ui/loader';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  fetchChatModels,
  fetchConversation,
  sendChatMessage,
  setChatModel,
  type ModelInfo,
} from '@/api/client';
import { useApp } from '@/context/AppContext';
import { errorMessage } from '@/lib/format';
import { PageHeader } from '@/components/layout/AppLayout';
import { ChatMessage, type UiMessage } from './ChatMessage';

const SUGGESTIONS = [
  'Riassumi i punti principali dei documenti',
  'Quali scadenze vengono citate?',
  'Elenca i requisiti richiesti',
  'Quali sono gli importi indicati?',
];

export function ChatPage() {
  const isAdmin = useAuthUser().app_metadata.chatbot_role === 'admin';
  const { id: routeId } = useParams();
  const navigate = useNavigate();
  const { knowledges, selectedKnowledgeId, setSelectedKnowledgeId, reloadConversations } = useApp();

  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [loadingConversation, setLoadingConversation] = useState(false);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [currentModel, setCurrentModel] = useState('');

  // Id della conversazione i cui messaggi sono già in stato: evita di
  // ricaricare dal server quando l'URL cambia dopo la prima risposta.
  const loadedIdRef = useRef<string | null>(null);
  const abortRef = useRef<{ aborted: boolean } | null>(null);

  useEffect(() => {
    fetchChatModels()
      .then((data) => {
        setModels(data.models);
        setCurrentModel(data.current);
      })
      .catch(() => setModels([]));
  }, []);

  // "Nuova chat": azzera durante il render quando si torna su "/" (niente effetto).
  const [prevRouteId, setPrevRouteId] = useState(routeId);
  if (routeId !== prevRouteId) {
    setPrevRouteId(routeId);
    if (!routeId) setMessages([]);
  }

  useEffect(() => {
    if (!routeId) {
      loadedIdRef.current = null;
      return;
    }
    if (routeId === loadedIdRef.current) return;

    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch della conversazione
    setLoadingConversation(true);
    fetchConversation(routeId)
      .then((conv) => {
        if (cancelled) return;
        loadedIdRef.current = conv.id;
        setMessages(
          conv.messages.map((m) => ({
            id: m.id,
            role: m.role,
            content: m.content,
            sources: m.sources ?? undefined,
            timestamp: m.timestamp ? new Date(m.timestamp) : new Date(),
          })),
        );
        if (conv.knowledge_id) setSelectedKnowledgeId(conv.knowledge_id);
      })
      .catch((err) => {
        if (cancelled) return;
        toast.error(errorMessage(err, 'Conversazione non trovata'));
        navigate('/', { replace: true });
      })
      .finally(() => !cancelled && setLoadingConversation(false));
    return () => {
      cancelled = true;
    };
  }, [routeId, navigate, setSelectedKnowledgeId]);

  const changeModel = async (value: string) => {
    const model = models.find((m) => `${m.provider}:${m.id}` === value);
    if (!model) return;
    try {
      await setChatModel(model.id, model.provider);
      setCurrentModel(model.id);
      toast.success(`Modello: ${model.name}`);
    } catch (err) {
      toast.error(errorMessage(err, 'Cambio modello non riuscito'));
    }
  };

  const send = async (text?: string) => {
    const question = (text ?? input).trim();
    if (!question || sending) return;

    const history = messages.map((m) => ({ role: m.role, content: m.content }));
    setInput('');
    setMessages((prev) => [
      ...prev,
      { id: `u-${Date.now()}`, role: 'user', content: question, timestamp: new Date() },
    ]);
    setSending(true);
    const token = { aborted: false };
    abortRef.current = token;

    try {
      const res = await sendChatMessage(
        question,
        history,
        5,
        selectedKnowledgeId ?? undefined,
        routeId ?? undefined,
      );
      if (token.aborted) return;
      setMessages((prev) => [
        ...prev,
        {
          id: `a-${Date.now()}`,
          role: 'assistant',
          content: res.answer,
          sources: res.sources,
          timestamp: new Date(),
        },
      ]);
      if (res.conversation_id && res.conversation_id !== routeId) {
        loadedIdRef.current = res.conversation_id;
        navigate(`/c/${res.conversation_id}`, { replace: true });
      }
      reloadConversations();
    } catch (err) {
      if (!token.aborted) toast.error(errorMessage(err, 'Errore durante la risposta'));
    } finally {
      if (abortRef.current === token) setSending(false);
    }
  };

  // Il backend non supporta ancora l'interruzione: smettiamo di attendere
  // la risposta lato client, la richiesta prosegue sul server.
  const stop = () => {
    if (abortRef.current) abortRef.current.aborted = true;
    setSending(false);
  };

  const currentModelValue = models.find((m) => m.id === currentModel);
  const providers = [...new Set(models.map((m) => m.provider))];
  const isEmpty = messages.length === 0 && !loadingConversation;
  const noKnowledge = knowledges.length === 0;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <PageHeader>
        {knowledges.length > 0 && (
          <Select
            value={selectedKnowledgeId ?? undefined}
            onValueChange={setSelectedKnowledgeId}
            disabled={!!routeId}
          >
            <SelectTrigger size="sm" className="max-w-48" aria-label="Knowledge base">
              <BookOpen className="text-muted-foreground" />
              <SelectValue placeholder="Knowledge base" />
            </SelectTrigger>
            <SelectContent>
              {knowledges.map((k) => (
                <SelectItem key={k.id} value={k.id}>
                  {k.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
        {models.length > 0 && (
          <Select
            value={currentModelValue ? `${currentModelValue.provider}:${currentModelValue.id}` : undefined}
            onValueChange={changeModel}
            disabled={!isAdmin}
          >
            <SelectTrigger size="sm" className="max-w-52" aria-label="Modello">
              <Cpu className="text-muted-foreground" />
              <SelectValue placeholder="Modello" />
            </SelectTrigger>
            <SelectContent>
              {providers.map((p) => (
                <SelectGroup key={p}>
                  <SelectLabel>{p === 'ollama' ? 'Locale (Ollama)' : p === 'deepseek' ? 'DeepSeek' : 'OpenAI'}</SelectLabel>
                  {models
                    .filter((m) => m.provider === p)
                    .map((m) => (
                      <SelectItem key={`${m.provider}:${m.id}`} value={`${m.provider}:${m.id}`}>
                        {m.name}
                      </SelectItem>
                    ))}
                </SelectGroup>
              ))}
            </SelectContent>
          </Select>
        )}
      </PageHeader>

      <ChatContainerRoot className="relative min-h-0 flex-1">
        <ChatContainerContent className="mx-auto max-w-3xl gap-8 px-4 py-8">
          {loadingConversation && (
            <div className="space-y-6">
              <Skeleton className="ml-auto h-10 w-2/3 rounded-3xl" />
              <Skeleton className="h-24 w-full" />
              <Skeleton className="ml-auto h-10 w-1/2 rounded-3xl" />
            </div>
          )}

          {isEmpty && (
            <div className="flex flex-1 flex-col items-center justify-center gap-6 pt-[12vh] text-center">
              <div className="space-y-2">
                <h2 className="text-2xl font-semibold tracking-tight">Cosa vuoi sapere?</h2>
                <p className="text-muted-foreground text-sm">
                  {noKnowledge ? (
                    <>
                      Non ci sono ancora documenti.{' '}
                      <Link to="/knowledge" className="text-foreground underline underline-offset-4">
                        {isAdmin ? "Crea una knowledge base" : "Nessuna knowledge base disponibile"}
                      </Link>{' '}
                      {isAdmin ? " e carica dei PDF." : ": chiedi a un amministratore di caricare i documenti."}
                    </>
                  ) : (
                    'Le risposte citano i documenti della knowledge base selezionata.'
                  )}
                </p>
              </div>
            </div>
          )}

          {messages.map((m) => (
            <ChatMessage key={m.id} message={m} knowledgeId={selectedKnowledgeId} />
          ))}

          {sending && (
            <div className="text-muted-foreground flex items-center gap-2 text-sm">
              <Loader variant="text-shimmer" text="Cerco nei documenti e preparo la risposta…" />
            </div>
          )}
        </ChatContainerContent>
        <div className="pointer-events-none absolute inset-x-0 bottom-4 flex justify-center">
          <ScrollButton className="pointer-events-auto shadow-sm" />
        </div>
      </ChatContainerRoot>

      <div className="mx-auto w-full max-w-3xl shrink-0 px-4 pb-4">
        {isEmpty && !noKnowledge && (
          <div className="mb-3 flex flex-wrap justify-center gap-2">
            {SUGGESTIONS.map((s) => (
              <PromptSuggestion key={s} size="sm" onClick={() => send(s)}>
                {s}
              </PromptSuggestion>
            ))}
          </div>
        )}
        <PromptInput
          value={input}
          onValueChange={setInput}
          isLoading={sending}
          onSubmit={() => send()}
          className="bg-background"
        >
          <PromptInputTextarea
            placeholder="Fai una domanda sui documenti…"
            aria-label="Messaggio"
          />
          <PromptInputActions className="justify-end pt-2">
            <PromptInputAction tooltip={sending ? 'Interrompi' : 'Invia (Invio)'}>
              <Button
                size="icon"
                className="size-8 rounded-full"
                onClick={sending ? stop : () => send()}
                disabled={!sending && !input.trim()}
                aria-label={sending ? 'Interrompi' : 'Invia'}
              >
                {sending ? <Square className="size-3.5 fill-current" /> : <ArrowUp className="size-4" />}
              </Button>
            </PromptInputAction>
          </PromptInputActions>
        </PromptInput>
        <p className="text-muted-foreground mt-2 text-center text-xs">
          Stai parlando con un assistente IA: verifica le informazioni importanti sulle fonti.
        </p>
      </div>
    </div>
  );
}
