import { useState, useEffect } from 'react';
import { fetchSystemPrompt, updateSystemPrompt, resetSystemPrompt, fetchDefaultPrompt, fetchEmbeddingModels, setEmbeddingModel, fetchProviderConfig, type ModelInfo } from '../api/client';

interface SettingsProps {
  onNavigate: (view: 'chat' | 'admin') => void;
}

const Settings: React.FC<SettingsProps> = ({ onNavigate }) => {
  const [prompt, setPrompt] = useState('');
  const [originalPrompt, setOriginalPrompt] = useState('');
  const [defaultPrompt, setDefaultPrompt] = useState('');
  const [isDefault, setIsDefault] = useState(true);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [hasChanges, setHasChanges] = useState(false);

  // Embedding model state
  const [embeddingModels, setEmbeddingModels] = useState<ModelInfo[]>([]);
  const [currentEmbeddingModel, setCurrentEmbeddingModel] = useState('');
  const [currentEmbeddingProvider, setCurrentEmbeddingProvider] = useState('');
  const [embeddingModelLoading, setEmbeddingModelLoading] = useState(false);
  const [ollamaAvailable, setOllamaAvailable] = useState(false);
  const [openaiAvailable, setOpenaiAvailable] = useState(false);

  useEffect(() => {
    loadPrompt();
    loadDefaultPrompt();
    loadEmbeddingModels();
    loadProviderConfig();
  }, []);

  const loadProviderConfig = async () => {
    try {
      const config = await fetchProviderConfig();
      setOllamaAvailable(config.ollama_available);
      setOpenaiAvailable(config.openai_available);
    } catch (err) {
      console.error('Errore caricamento config provider:', err);
    }
  };

  const loadEmbeddingModels = async () => {
    try {
      const data = await fetchEmbeddingModels();
      setEmbeddingModels(data.models);
      setCurrentEmbeddingModel(data.current);
      setCurrentEmbeddingProvider(data.provider);
    } catch (err) {
      console.error('Errore caricamento modelli embedding:', err);
    }
  };

  const handleEmbeddingModelChange = async (model: ModelInfo) => {
    setEmbeddingModelLoading(true);
    setError(null);
    try {
      await setEmbeddingModel(model.id, model.provider);
      setCurrentEmbeddingModel(model.id);
      setCurrentEmbeddingProvider(model.provider);
      setSuccess(`Modello embedding impostato a ${model.name}`);
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Errore cambio modello embedding');
    } finally {
      setEmbeddingModelLoading(false);
    }
  };

  useEffect(() => {
    setHasChanges(prompt !== originalPrompt);
  }, [prompt, originalPrompt]);

  const loadPrompt = async () => {
    try {
      setLoading(true);
      const data = await fetchSystemPrompt();
      setPrompt(data.prompt);
      setOriginalPrompt(data.prompt);
      setIsDefault(data.is_default);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Errore caricamento prompt');
    } finally {
      setLoading(false);
    }
  };

  const loadDefaultPrompt = async () => {
    try {
      const data = await fetchDefaultPrompt();
      setDefaultPrompt(data.prompt);
    } catch (err) {
      console.error('Errore caricamento prompt default:', err);
    }
  };

  const handleSave = async () => {
    if (!prompt.trim()) {
      setError('Il prompt non può essere vuoto');
      return;
    }

    try {
      setSaving(true);
      setError(null);
      setSuccess(null);
      await updateSystemPrompt(prompt);
      setOriginalPrompt(prompt);
      setIsDefault(prompt === defaultPrompt);
      setSuccess('Prompt salvato con successo!');
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Errore salvataggio prompt');
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    if (!confirm('Sei sicuro di voler ripristinare il prompt di default? Le modifiche attuali andranno perse.')) {
      return;
    }

    try {
      setSaving(true);
      setError(null);
      setSuccess(null);
      await resetSystemPrompt();
      setPrompt(defaultPrompt);
      setOriginalPrompt(defaultPrompt);
      setIsDefault(true);
      setSuccess('Prompt ripristinato al valore di default!');
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Errore ripristino prompt');
    } finally {
      setSaving(false);
    }
  };

  const handleDiscard = () => {
    setPrompt(originalPrompt);
    setError(null);
  };

  return (
    <div className="flex h-full w-full bg-admin-bg font-display text-[#0d181c] overflow-hidden">
      
      {/* Sidebar */}
      <aside className="w-64 flex-shrink-0 bg-admin-bg border-r border-[#cee2e9] flex flex-col justify-between h-full hidden md:flex">
        <div className="p-6 flex flex-col gap-8">
          {/* Logo */}
          <div className="flex items-center gap-3 cursor-pointer" onClick={() => onNavigate('chat')}>
            <div className="flex items-center justify-center h-10 w-10 rounded-full bg-admin-primary/20">
              <span className="material-symbols-filled text-admin-primary text-[24px]">smart_toy</span>
            </div>
            <div className="flex flex-col">
              <h1 className="text-[#0d181c] text-base font-bold leading-normal">Intecha</h1>
              <p className="text-admin-text-secondary text-xs font-normal leading-normal">Admin Panel</p>
            </div>
          </div>
          
          {/* Navigation */}
          <nav className="flex flex-col gap-2">
            <button onClick={() => onNavigate('chat')} className="flex items-center gap-3 px-3 py-2 rounded-lg text-[#0d181c] hover:bg-[#e6f1f4] transition-colors group">
              <span className="material-symbols-outlined text-admin-text-secondary group-hover:text-admin-primary transition-colors">chat_bubble</span>
              <span className="text-sm font-medium">Chat AI</span>
            </button>
            <button onClick={() => onNavigate('admin')} className="flex items-center gap-3 px-3 py-2 rounded-lg text-[#0d181c] hover:bg-[#e6f1f4] transition-colors group">
              <span className="material-symbols-outlined text-admin-text-secondary group-hover:text-admin-primary transition-colors">description</span>
              <span className="text-sm font-medium">Knowledge Base</span>
            </button>
            <a href="#" className="flex items-center gap-3 px-3 py-2 rounded-lg bg-admin-primary/10 text-admin-primary transition-colors">
              <span className="material-symbols-filled">settings</span>
              <span className="text-sm font-medium">Impostazioni</span>
            </a>
          </nav>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col h-full overflow-hidden relative">
        {/* Header Section */}
        <header className="flex-shrink-0 px-8 py-6 bg-admin-bg z-10 border-b border-[#cee2e9]">
          <div className="max-w-4xl mx-auto">
            <div className="flex justify-between items-center">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <button onClick={() => onNavigate('chat')} className="md:hidden p-1 rounded-md hover:bg-slate-100">
                    <span className="material-symbols-outlined text-[#0d181b]">arrow_back</span>
                  </button>
                  <h2 className="text-2xl font-bold tracking-tight text-[#0d181c]">Impostazioni</h2>
                </div>
                <p className="text-admin-text-secondary mt-1">Configura il comportamento dell'assistente AI</p>
              </div>
              <div className="flex items-center gap-2">
                {!isDefault && (
                  <span className="px-2 py-1 rounded-md bg-yellow-50 text-yellow-700 text-xs font-medium">
                    Personalizzato
                  </span>
                )}
              </div>
            </div>
          </div>
        </header>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-8 py-6">
          <div className="max-w-4xl mx-auto">
            
            {/* Error/Success Messages */}
            {error && (
              <div className="mb-6 px-4 py-3 rounded-lg bg-red-50 border border-red-200 text-red-600 text-sm flex items-center gap-2">
                <span className="material-symbols-outlined text-[18px]">error</span>
                {error}
              </div>
            )}
            {success && (
              <div className="mb-6 px-4 py-3 rounded-lg bg-green-50 border border-green-200 text-green-600 text-sm flex items-center gap-2">
                <span className="material-symbols-outlined text-[18px]">check_circle</span>
                {success}
              </div>
            )}

            {/* Prompt Section */}
            <div className="bg-white rounded-xl border border-[#cee2e9] shadow-sm">
              <div className="p-6 border-b border-[#cee2e9]">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-lg font-bold text-[#0d181c] flex items-center gap-2">
                      <span className="material-symbols-outlined text-admin-primary">psychology</span>
                      Prompt di Sistema
                    </h3>
                    <p className="text-sm text-admin-text-secondary mt-1">
                      Definisce la personalità e le regole di comportamento dell'assistente AI
                    </p>
                  </div>
                </div>
              </div>

              <div className="p-6">
                {loading ? (
                  <div className="flex items-center justify-center py-12">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-admin-primary"></div>
                  </div>
                ) : (
                  <>
                    <textarea
                      value={prompt}
                      onChange={(e) => setPrompt(e.target.value)}
                      className="w-full h-[400px] p-4 border border-[#cee2e9] rounded-lg text-sm text-[#0d181c] font-mono leading-relaxed resize-none focus:outline-none focus:ring-2 focus:ring-admin-primary/20 focus:border-admin-primary"
                      placeholder="Inserisci il prompt di sistema..."
                    />

                    <div className="mt-4 flex items-center justify-between">
                      <div className="text-xs text-admin-text-secondary">
                        {prompt.length} caratteri
                      </div>
                      <div className="flex items-center gap-3">
                        {hasChanges && (
                          <button
                            onClick={handleDiscard}
                            disabled={saving}
                            className="px-4 py-2 rounded-lg border border-[#cee2e9] text-sm font-medium text-admin-text-secondary hover:bg-gray-50 transition-colors disabled:opacity-50"
                          >
                            Annulla modifiche
                          </button>
                        )}
                        <button
                          onClick={handleReset}
                          disabled={saving || isDefault}
                          className="px-4 py-2 rounded-lg border border-[#cee2e9] text-sm font-medium text-admin-text-secondary hover:bg-gray-50 transition-colors disabled:opacity-50 flex items-center gap-2"
                        >
                          <span className="material-symbols-outlined text-[18px]">restart_alt</span>
                          Ripristina default
                        </button>
                        <button
                          onClick={handleSave}
                          disabled={saving || !hasChanges}
                          className="px-5 py-2 rounded-lg bg-admin-primary text-white text-sm font-semibold hover:brightness-95 transition-all shadow-md shadow-admin-primary/20 disabled:opacity-50 flex items-center gap-2"
                        >
                          {saving ? (
                            <>
                              <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                              Salvataggio...
                            </>
                          ) : (
                            <>
                              <span className="material-symbols-outlined text-[18px]">save</span>
                              Salva modifiche
                            </>
                          )}
                        </button>
                      </div>
                    </div>
                  </>
                )}
              </div>
            </div>

            {/* Embedding Model Section */}
            <div className="mt-6 bg-white rounded-xl border border-[#cee2e9] shadow-sm">
              <div className="p-6 border-b border-[#cee2e9]">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-lg font-bold text-[#0d181c] flex items-center gap-2">
                      <span className="material-symbols-outlined text-admin-primary">data_array</span>
                      Modello Embedding
                    </h3>
                    <p className="text-sm text-admin-text-secondary mt-1">
                      Seleziona il modello utilizzato per generare gli embedding dei documenti
                    </p>
                  </div>
                  {/* Status badge */}
                  <div className="flex items-center gap-2">
                    <div className="flex items-center gap-1.5">
                      <div className={`h-2 w-2 rounded-full ${openaiAvailable ? 'bg-emerald-500' : 'bg-gray-300'}`}></div>
                      <span className="text-xs text-admin-text-secondary">OpenAI</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <div className={`h-2 w-2 rounded-full ${ollamaAvailable ? 'bg-emerald-500' : 'bg-gray-300'}`}></div>
                      <span className="text-xs text-admin-text-secondary">Ollama</span>
                    </div>
                  </div>
                </div>
              </div>

              <div className="p-6">
                {embeddingModels.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-8 text-center">
                    <span className="material-symbols-outlined text-[40px] text-admin-text-secondary mb-3">cloud_off</span>
                    <p className="text-sm text-admin-text-secondary">
                      Nessun modello embedding disponibile. Verifica che OpenAI o Ollama siano configurati.
                    </p>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {embeddingModels.map((model) => {
                      const isSelected = model.id === currentEmbeddingModel && model.provider === currentEmbeddingProvider;
                      return (
                        <button
                          key={`${model.provider}-${model.id}`}
                          onClick={() => handleEmbeddingModelChange(model)}
                          disabled={embeddingModelLoading}
                          className={`flex items-center gap-4 p-4 rounded-xl border-2 transition-all text-left ${
                            isSelected
                              ? 'border-admin-primary bg-admin-primary/5 shadow-sm'
                              : 'border-[#cee2e9] hover:border-admin-primary/40 hover:bg-gray-50'
                          } ${embeddingModelLoading ? 'opacity-50 cursor-not-allowed' : ''}`}
                        >
                          <div className={`flex items-center justify-center size-10 rounded-lg ${
                            model.provider === 'ollama' ? 'bg-purple-100' : 'bg-emerald-100'
                          }`}>
                            <span className={`material-symbols-outlined text-[22px] ${
                              model.provider === 'ollama' ? 'text-purple-600' : 'text-emerald-600'
                            }`}>
                              {model.provider === 'ollama' ? 'memory' : 'cloud'}
                            </span>
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-semibold text-[#0d181c] truncate">{model.name}</p>
                            <div className="flex items-center gap-2 mt-0.5">
                              <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                                model.provider === 'ollama' ? 'bg-purple-100 text-purple-700' : 'bg-emerald-100 text-emerald-700'
                              }`}>
                                {model.provider}
                              </span>
                              <span className="text-xs text-admin-text-secondary truncate">{model.id}</span>
                            </div>
                          </div>
                          {isSelected && (
                            <span className="material-symbols-outlined text-admin-primary text-[22px] shrink-0">check_circle</span>
                          )}
                        </button>
                      );
                    })}
                  </div>
                )}

                {currentEmbeddingModel && (
                  <div className="mt-4 px-4 py-3 rounded-lg bg-blue-50 border border-blue-100 text-sm text-blue-700 flex items-center gap-2">
                    <span className="material-symbols-outlined text-[18px]">info</span>
                    <span>
                      <strong>Attenzione:</strong> cambiare il modello di embedding richiede la re-indicizzazione dei documenti 
                      (le dimensioni dei vettori potrebbero cambiare).
                    </span>
                  </div>
                )}
              </div>
            </div>

            {/* Help Section */}
            <div className="mt-6 bg-gradient-to-br from-admin-primary/5 to-transparent p-6 rounded-xl border border-admin-primary/20">
              <h4 className="font-bold text-[#0d181c] flex items-center gap-2 mb-3">
                <span className="material-symbols-outlined text-admin-primary">tips_and_updates</span>
                Suggerimenti per un buon prompt
              </h4>
              <ul className="space-y-2 text-sm text-admin-text-secondary">
                <li className="flex items-start gap-2">
                  <span className="material-symbols-outlined text-[16px] text-admin-primary mt-0.5">check</span>
                  <span>Definisci chiaramente il <strong>ruolo</strong> dell'assistente (es: "Sei un assistente competente...")</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="material-symbols-outlined text-[16px] text-admin-primary mt-0.5">check</span>
                  <span>Specifica le <strong>regole</strong> per le risposte (citare fonti, non inventare, ecc.)</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="material-symbols-outlined text-[16px] text-admin-primary mt-0.5">check</span>
                  <span>Indica il <strong>tono</strong> da usare (formale, professionale, cordiale)</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="material-symbols-outlined text-[16px] text-admin-primary mt-0.5">check</span>
                  <span>Ricorda che il prompt viene inviato all'inizio di ogni conversazione</span>
                </li>
              </ul>
            </div>

          </div>
        </div>
      </main>
    </div>
  );
};

export default Settings;
