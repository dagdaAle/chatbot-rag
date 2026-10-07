import { useAuthUser } from '@/auth/AuthContext';
import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Loader2, RotateCcw, Save, ShieldCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  fetchEmbeddingModels,
  fetchProviderConfig,
  fetchSystemPrompt,
  resetSystemPrompt,
  setEmbeddingModel,
  updateSystemPrompt,
  type ModelInfo,
  type ProviderConfigResponse,
} from '@/api/client';
import { errorMessage } from '@/lib/format';
import { PageHeader } from '@/components/layout/AppLayout';

export function SettingsPage() {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <PageHeader title="Impostazioni" />
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl p-4 md:p-6">
          <Tabs defaultValue="models">
            <TabsList>
              <TabsTrigger value="models">Modelli</TabsTrigger>
              <TabsTrigger value="prompt">Prompt di sistema</TabsTrigger>
              <TabsTrigger value="privacy">Privacy</TabsTrigger>
            </TabsList>
            <TabsContent value="models" className="mt-4">
              <ModelsSettings />
            </TabsContent>
            <TabsContent value="prompt" className="mt-4">
              <PromptSettings />
            </TabsContent>
            <TabsContent value="privacy" className="mt-4">
              <PrivacySettings />
            </TabsContent>
          </Tabs>
        </div>
      </div>
    </div>
  );
}

function ModelsSettings() {
  const isAdmin = useAuthUser().app_metadata.chatbot_role === 'admin';
  const [config, setConfig] = useState<ProviderConfigResponse | null>(null);
  const [embeddings, setEmbeddings] = useState<ModelInfo[]>([]);
  const [currentEmbedding, setCurrentEmbedding] = useState('');

  useEffect(() => {
    fetchProviderConfig().then(setConfig).catch(() => setConfig(null));
    fetchEmbeddingModels()
      .then((d) => {
        setEmbeddings(d.models);
        setCurrentEmbedding(d.current);
      })
      .catch(() => setEmbeddings([]));
  }, []);

  const changeEmbedding = async (value: string) => {
    const model = embeddings.find((m) => `${m.provider}:${m.id}` === value);
    if (!model) return;
    try {
      await setEmbeddingModel(model.id, model.provider);
      setCurrentEmbedding(model.id);
      toast.success(`Embedding: ${model.name}`, {
        description: 'Le knowledge base già indicizzate vanno ricaricate con il nuovo modello.',
      });
    } catch (err) {
      toast.error(errorMessage(err, 'Cambio modello non riuscito'));
    }
  };

  const current = embeddings.find((m) => m.id === currentEmbedding);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Provider</CardTitle>
          <CardDescription>Il modello di chat è condiviso e viene configurato dagli amministratori.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <Badge variant={config?.ollama_available ? 'default' : 'outline'}>
            Ollama {config?.ollama_available ? 'attivo' : 'non raggiungibile'}
          </Badge>
          <Badge variant={config?.deepseek_available ? 'default' : 'outline'}>
            DeepSeek {config?.deepseek_available ? 'configurato' : 'non configurato'}
          </Badge>
          {config?.openai_available && <Badge>OpenAI configurato</Badge>}
          {config && <Badge variant="secondary">Chat: {config.chat_model}</Badge>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Modello di embedding</CardTitle>
          <CardDescription>
            Trasforma testi e domande in vettori. Cambiarlo rende incompatibili gli indici esistenti.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Select
            value={current ? `${current.provider}:${current.id}` : undefined}
            onValueChange={changeEmbedding}
            disabled={!isAdmin}
          >
            <SelectTrigger className="w-full sm:w-80" aria-label="Modello di embedding">
              <SelectValue placeholder="Seleziona" />
            </SelectTrigger>
            <SelectContent>
              {embeddings.map((m) => (
                <SelectItem key={`${m.provider}:${m.id}`} value={`${m.provider}:${m.id}`}>
                  {m.name} · {m.provider}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </CardContent>
      </Card>
    </div>
  );
}

function PromptSettings() {
  const isAdmin = useAuthUser().app_metadata.chatbot_role === 'admin';
  const [prompt, setPrompt] = useState('');
  const [original, setOriginal] = useState('');
  const [isDefault, setIsDefault] = useState(true);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchSystemPrompt()
      .then((d) => {
        setPrompt(d.prompt);
        setOriginal(d.prompt);
        setIsDefault(d.is_default);
      })
      .catch((err) => toast.error(errorMessage(err, 'Errore caricamento prompt')))
      .finally(() => setLoading(false));
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      await updateSystemPrompt(prompt);
      setOriginal(prompt);
      setIsDefault(false);
      toast.success('Prompt salvato');
    } catch (err) {
      toast.error(errorMessage(err, 'Salvataggio non riuscito'));
    } finally {
      setSaving(false);
    }
  };

  const reset = async () => {
    try {
      await resetSystemPrompt();
      const d = await fetchSystemPrompt();
      setPrompt(d.prompt);
      setOriginal(d.prompt);
      setIsDefault(true);
      toast.success('Ripristinato il prompt predefinito');
    } catch (err) {
      toast.error(errorMessage(err, 'Ripristino non riuscito'));
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          Prompt di sistema {isDefault && <Badge variant="secondary">predefinito</Badge>}
        </CardTitle>
        <CardDescription>Le istruzioni che il modello riceve prima di ogni domanda.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <Label htmlFor="system-prompt" className="sr-only">
          Prompt di sistema
        </Label>
        <Textarea
          id="system-prompt"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          disabled={loading || !isAdmin}
          className="min-h-80 font-mono text-xs leading-relaxed"
        />
        <div className="flex flex-wrap justify-end gap-2">
          <Button variant="outline" onClick={reset} disabled={loading || isDefault || !isAdmin}>
            <RotateCcw /> Ripristina predefinito
          </Button>
          <Button onClick={save} disabled={saving || prompt === original || !isAdmin}>
            {saving ? <Loader2 className="animate-spin" /> : <Save />} Salva
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function PrivacySettings() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ShieldCheck className="size-5" /> Anonimizzazione
          <Badge variant="outline">non ancora collegata</Badge>
        </CardTitle>
        <CardDescription>
          Il servizio di anonimizzazione è attivo sul server ma il backend del chatbot non lo usa
          ancora. Quando sarà collegato potrai scegliere la modalità per ogni knowledge base.
        </CardDescription>
      </CardHeader>
      <CardContent className="text-muted-foreground space-y-2 text-sm">
        <p>
          <span className="text-foreground font-medium">Spenta</span> — i testi vengono indicizzati
          così come sono.
        </p>
        <p>
          <span className="text-foreground font-medium">Redazione</span> — i dati personali diventano{' '}
          <code className="bg-muted rounded px-1">&lt;PERSONA&gt;</code>, in modo irreversibile.
        </p>
        <p>
          <span className="text-foreground font-medium">Pseudonimi</span> —{' '}
          <code className="bg-muted rounded px-1">&lt;PERSONA_1&gt;</code>, con i nomi veri rimessi
          nella risposta. I dati restano personali ai fini del GDPR.
        </p>
      </CardContent>
    </Card>
  );
}
