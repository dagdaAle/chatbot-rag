import { useState, useEffect, useRef, useCallback } from 'react';
import {
  fetchKnowledges,
  createKnowledge,
  deleteKnowledge,
  fetchDocuments,
  uploadDocuments,
  deleteDocument,
  fetchHealthQdrant,
  type KnowledgeItem,
  type DocumentItem,
} from '../api/client';

interface KnowledgeBaseProps {
  onNavigate: () => void;
  onSettings: () => void;
}

/* ────────────────────────────────────────────────────────── */
/*  Componente principale                                    */
/* ────────────────────────────────────────────────────────── */
const KnowledgeBase: React.FC<KnowledgeBaseProps> = ({ onNavigate, onSettings }) => {
  // Knowledge list state
  const [knowledges, setKnowledges] = useState<KnowledgeItem[]>([]);
  const [loadingKB, setLoadingKB] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Create Knowledge modal
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newKBName, setNewKBName] = useState('');
  const [newKBDesc, setNewKBDesc] = useState('');
  const [creating, setCreating] = useState(false);

  // Selected Knowledge detail view
  const [selectedKB, setSelectedKB] = useState<KnowledgeItem | null>(null);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [loadingDocs, setLoadingDocs] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Qdrant status
  const [qdrantStatus, setQdrantStatus] = useState<'loading' | 'ok' | 'error'>('loading');
  const [collectionsCount, setCollectionsCount] = useState(0);

  // Search
  const [searchQuery, setSearchQuery] = useState('');

  /* ── Caricamento Knowledge ── */
  const loadKnowledges = useCallback(async () => {
    try {
      setLoadingKB(true);
      const data = await fetchKnowledges();
      setKnowledges(data.knowledges);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Errore caricamento knowledge');
    } finally {
      setLoadingKB(false);
    }
  }, []);

  useEffect(() => {
    loadKnowledges();
    fetchHealthQdrant()
      .then((data) => {
        setQdrantStatus('ok');
        setCollectionsCount(data.collections_count ?? 0);
      })
      .catch(() => setQdrantStatus('error'));
  }, [loadKnowledges]);

  /* ── Crea Knowledge ── */
  const handleCreateKB = async () => {
    if (!newKBName.trim()) return;
    setCreating(true);
    setError(null);
    try {
      await createKnowledge(newKBName.trim(), newKBDesc.trim());
      setNewKBName('');
      setNewKBDesc('');
      setShowCreateModal(false);
      await loadKnowledges();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Errore creazione knowledge');
    } finally {
      setCreating(false);
    }
  };

  /* ── Elimina Knowledge ── */
  const handleDeleteKB = async (kbId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm('Sei sicuro di voler eliminare questa Knowledge e tutti i suoi documenti?')) return;
    try {
      await deleteKnowledge(kbId);
      if (selectedKB?.id === kbId) {
        setSelectedKB(null);
        setDocuments([]);
      }
      await loadKnowledges();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Errore eliminazione knowledge');
    }
  };

  /* ── Seleziona Knowledge → carica documenti ── */
  const handleSelectKB = async (kb: KnowledgeItem) => {
    setSelectedKB(kb);
    setLoadingDocs(true);
    try {
      const data = await fetchDocuments(kb.id);
      setDocuments(data.documents);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Errore caricamento documenti');
    } finally {
      setLoadingDocs(false);
    }
  };

  /* ── Upload multiplo documenti ── */
  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const fileList = e.target.files;
    if (!fileList || fileList.length === 0 || !selectedKB) return;

    setUploading(true);
    setError(null);
    setUploadProgress(`Caricamento di ${fileList.length} file...`);

    try {
      const files = Array.from(fileList);
      const result = await uploadDocuments(selectedKB.id, files);

      if (result.total_errors > 0) {
        const errMsgs = result.errors.map((e) => `${e.filename}: ${e.error}`).join('; ');
        setError(`Errori: ${errMsgs}`);
      }
      setUploadProgress(`${result.total_uploaded} file caricati con successo`);

      // Ricarica documenti e knowledge
      const data = await fetchDocuments(selectedKB.id);
      setDocuments(data.documents);
      await loadKnowledges();

      setTimeout(() => setUploadProgress(''), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Errore durante il caricamento');
      setUploadProgress('');
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  /* ── Elimina documento ── */
  const handleDeleteDoc = async (documentId: string) => {
    if (!selectedKB) return;
    if (!confirm('Sei sicuro di voler eliminare questo documento?')) return;
    try {
      await deleteDocument(selectedKB.id, documentId);
      const data = await fetchDocuments(selectedKB.id);
      setDocuments(data.documents);
      await loadKnowledges();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Errore durante l'eliminazione");
    }
  };

  /* ── Helpers ── */
  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diffTime = now.getTime() - date.getTime();
    const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));
    if (diffDays === 0) return 'Oggi';
    if (diffDays === 1) return 'Ieri';
    return date.toLocaleDateString('it-IT', { day: 'numeric', month: 'short', year: 'numeric' });
  };

  const filteredKnowledges = knowledges.filter(
    (kb) =>
      kb.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      kb.description.toLowerCase().includes(searchQuery.toLowerCase()),
  );

  const totalDocs = knowledges.reduce((sum, kb) => sum + kb.documents_count, 0);

  /* ────────────────────────────────────────────────────────── */
  /*  RENDER                                                   */
  /* ────────────────────────────────────────────────────────── */
  return (
    <div className="flex h-full w-full bg-admin-bg font-display text-[#0d181c] overflow-hidden">
      {/* ─── Sidebar ─── */}
      <aside className="w-64 flex-shrink-0 bg-admin-bg border-r border-[#cee2e9] flex flex-col justify-between h-full hidden md:flex">
        <div className="p-6 flex flex-col gap-8">
          <div className="flex items-center gap-3 cursor-pointer" onClick={onNavigate}>
            <div className="flex items-center justify-center h-10 w-10 rounded-full bg-admin-primary/20">
              <span className="material-symbols-filled text-admin-primary text-[24px]">smart_toy</span>
            </div>
            <div className="flex flex-col">
              <h1 className="text-[#0d181c] text-base font-bold leading-normal">Intecha</h1>
              <p className="text-admin-text-secondary text-xs font-normal leading-normal">Admin Panel</p>
            </div>
          </div>
          <nav className="flex flex-col gap-2">
            <button onClick={onNavigate} className="flex items-center gap-3 px-3 py-2 rounded-lg text-[#0d181c] hover:bg-[#e6f1f4] transition-colors group">
              <span className="material-symbols-outlined text-admin-text-secondary group-hover:text-admin-primary transition-colors">chat_bubble</span>
              <span className="text-sm font-medium">Chat AI</span>
            </button>
            <a href="#" className="flex items-center gap-3 px-3 py-2 rounded-lg bg-admin-primary/10 text-admin-primary transition-colors">
              <span className="material-symbols-filled">description</span>
              <span className="text-sm font-medium">Knowledge Base</span>
            </a>
            <button onClick={onSettings} className="flex items-center gap-3 px-3 py-2 rounded-lg text-[#0d181c] hover:bg-[#e6f1f4] transition-colors group">
              <span className="material-symbols-outlined text-admin-text-secondary group-hover:text-admin-primary transition-colors">settings</span>
              <span className="text-sm font-medium">Impostazioni</span>
            </button>
          </nav>
        </div>
        <div className="p-4 border-t border-[#cee2e9]">
          <div className="flex items-center gap-3 px-2 py-2">
            <div className={`h-2 w-2 rounded-full ${qdrantStatus === 'ok' ? 'bg-emerald-500' : qdrantStatus === 'error' ? 'bg-red-500' : 'bg-yellow-400 animate-pulse'}`}></div>
            <div className="flex flex-col">
              <p className="text-[#0d181c] text-sm font-medium">Qdrant</p>
              <p className="text-admin-text-secondary text-xs">
                {qdrantStatus === 'ok' ? `${collectionsCount} collections` : qdrantStatus === 'error' ? 'Non connesso' : 'Connessione...'}
              </p>
            </div>
          </div>
        </div>
      </aside>

      {/* ─── Main Content ─── */}
      <main className="flex-1 flex flex-col h-full overflow-hidden relative">
        {/* Header */}
        <header className="flex-shrink-0 px-8 py-6 bg-admin-bg z-10">
          <div className="max-w-7xl mx-auto flex flex-col gap-6">
            <div className="flex justify-between items-end">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <button onClick={() => selectedKB ? setSelectedKB(null) : onNavigate()} className="md:hidden p-1 rounded-md hover:bg-slate-100">
                    <span className="material-symbols-outlined text-[#0d181b]">arrow_back</span>
                  </button>
                  <h2 className="text-2xl font-bold tracking-tight text-[#0d181c]">
                    {selectedKB ? selectedKB.name : 'Knowledge Base'}
                  </h2>
                </div>
                <p className="text-admin-text-secondary mt-1">
                  {selectedKB ? `${documents.length} documenti caricati` : 'Gestisci le tue raccolte di documenti'}
                </p>
              </div>
              {selectedKB && (
                <button
                  onClick={() => { setSelectedKB(null); setDocuments([]); }}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg border border-[#cee2e9] hover:bg-[#e6f1f4] transition-colors text-sm font-medium"
                >
                  <span className="material-symbols-outlined text-[18px]">arrow_back</span>
                  Tutte le Knowledge
                </button>
              )}
            </div>

            {/* Stats Grid */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="bg-white p-5 rounded-xl border border-[#cee2e9] shadow-sm flex flex-col gap-1">
                <div className="flex items-center justify-between">
                  <span className="text-admin-text-secondary text-sm font-medium">
                    {selectedKB ? 'Documenti' : 'Knowledge'}
                  </span>
                  <span className="material-symbols-outlined text-admin-primary bg-admin-primary/10 p-1 rounded-md text-[20px]">
                    {selectedKB ? 'folder_open' : 'auto_stories'}
                  </span>
                </div>
                <div className="flex items-end gap-2 mt-2">
                  <span className="text-2xl font-bold text-[#0d181c]">
                    {selectedKB ? documents.length : knowledges.length}
                  </span>
                </div>
              </div>

              <div className="bg-white p-5 rounded-xl border border-[#cee2e9] shadow-sm flex flex-col gap-1">
                <div className="flex items-center justify-between">
                  <span className="text-admin-text-secondary text-sm font-medium">
                    {selectedKB ? 'Chunks Totali' : 'Documenti Totali'}
                  </span>
                  <span className="material-symbols-outlined text-admin-primary bg-admin-primary/10 p-1 rounded-md text-[20px]">data_array</span>
                </div>
                <div className="flex items-end gap-2 mt-2">
                  <span className="text-2xl font-bold text-[#0d181c]">
                    {selectedKB ? documents.reduce((s, d) => s + d.chunks_count, 0) : totalDocs}
                  </span>
                  <span className="text-admin-text-secondary text-xs mb-1">
                    {selectedKB ? 'vettori indicizzati' : 'in tutte le knowledge'}
                  </span>
                </div>
              </div>

              <div className="bg-white p-5 rounded-xl border border-[#cee2e9] shadow-sm flex flex-col gap-1">
                <div className="flex items-center justify-between">
                  <span className="text-admin-text-secondary text-sm font-medium">Stato Sistema</span>
                  <span className="material-symbols-outlined text-admin-primary bg-admin-primary/10 p-1 rounded-md text-[20px]">dns</span>
                </div>
                <div className="flex items-end gap-2 mt-2">
                  <div className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-green-50 border border-green-100">
                    <div className={`w-1.5 h-1.5 rounded-full ${qdrantStatus === 'ok' ? 'bg-[#078836]' : 'bg-red-500'}`}></div>
                    <span className={`text-xs font-medium ${qdrantStatus === 'ok' ? 'text-[#078836]' : 'text-red-500'}`}>
                      {qdrantStatus === 'ok' ? 'Operativo' : 'Errore'}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* Action Bar */}
            <div className="flex flex-col sm:flex-row gap-4 justify-between items-center mt-2">
              {!selectedKB && (
                <div className="relative w-full sm:max-w-md group">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <span className="material-symbols-outlined text-admin-text-secondary">search</span>
                  </div>
                  <input
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="block w-full pl-10 pr-3 py-2.5 border-none rounded-lg leading-5 bg-white text-[#0d181c] placeholder-admin-text-secondary focus:outline-none focus:ring-2 focus:ring-admin-primary shadow-sm ring-1 ring-[#cee2e9] sm:text-sm transition-shadow"
                    placeholder="Cerca knowledge..."
                    type="text"
                  />
                </div>
              )}
              <div className="flex gap-2 w-full sm:w-auto">
                {selectedKB ? (
                  <>
                    <input
                      ref={fileInputRef}
                      type="file"
                      onChange={handleFileUpload}
                      accept=".pdf"
                      multiple
                      className="hidden"
                      id="file-upload"
                    />
                    <label
                      htmlFor="file-upload"
                      className={`flex items-center justify-center gap-2 bg-admin-primary hover:brightness-95 text-white px-5 py-2.5 rounded-lg shadow-md shadow-admin-primary/20 transition-all active:scale-95 w-full sm:w-auto cursor-pointer ${uploading ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                      <span className="material-symbols-outlined text-[20px]">
                        {uploading ? 'hourglass_empty' : 'upload_file'}
                      </span>
                      <span className="font-semibold text-sm">
                        {uploading ? 'Caricamento...' : 'Carica Documenti'}
                      </span>
                    </label>
                  </>
                ) : (
                  <button
                    onClick={() => setShowCreateModal(true)}
                    className="flex items-center justify-center gap-2 bg-admin-primary hover:brightness-95 text-white px-5 py-2.5 rounded-lg shadow-md shadow-admin-primary/20 transition-all active:scale-95 w-full sm:w-auto"
                  >
                    <span className="material-symbols-outlined text-[20px]">add</span>
                    <span className="font-semibold text-sm">Nuova Knowledge</span>
                  </button>
                )}
              </div>
            </div>

            {/* Upload progress / Error */}
            {uploadProgress && (
              <div className="px-4 py-3 rounded-lg bg-blue-50 border border-blue-200 text-blue-700 text-sm">
                {uploadProgress}
              </div>
            )}
            {error && (
              <div className="px-4 py-3 rounded-lg bg-red-50 border border-red-200 text-red-600 text-sm">
                {error}
              </div>
            )}
          </div>
        </header>

        {/* ─── Scrollable Content ─── */}
        <div className="flex-1 overflow-y-auto px-8 pb-8">
          <div className="max-w-7xl mx-auto h-full">
            {selectedKB ? (
              /* ═══ DOCUMENTS LIST ═══ */
              <div className="bg-white rounded-xl border border-[#cee2e9] shadow-sm flex flex-col overflow-hidden">
                {loadingDocs ? (
                  <div className="flex items-center justify-center py-20">
                    <div className="flex flex-col items-center gap-3">
                      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-admin-primary"></div>
                      <span className="text-admin-text-secondary text-sm">Caricamento documenti...</span>
                    </div>
                  </div>
                ) : documents.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-20 text-center">
                    <span className="material-symbols-outlined text-[48px] text-admin-text-secondary mb-4">folder_off</span>
                    <h3 className="text-lg font-semibold text-[#0d181c] mb-2">Nessun documento</h3>
                    <p className="text-admin-text-secondary text-sm max-w-md">
                      Carica i tuoi primi documenti PDF per iniziare a popolare questa Knowledge Base.
                    </p>
                  </div>
                ) : (
                  <>
                    <div className="overflow-x-auto">
                      <table className="min-w-full divide-y divide-[#cee2e9]">
                        <thead className="bg-gray-50">
                          <tr>
                            <th className="px-6 py-3 text-left text-xs font-medium text-admin-text-secondary uppercase tracking-wider w-12">Tipo</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-admin-text-secondary uppercase tracking-wider">Nome Documento</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-admin-text-secondary uppercase tracking-wider">Chunks</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-admin-text-secondary uppercase tracking-wider">Data</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-admin-text-secondary uppercase tracking-wider">Status</th>
                            <th className="relative px-6 py-3"><span className="sr-only">Azioni</span></th>
                          </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-[#cee2e9]">
                          {documents.map((doc) => (
                            <tr key={doc.document_id} className="hover:bg-gray-50 transition-colors group">
                              <td className="px-6 py-4 whitespace-nowrap">
                                <div className="flex items-center justify-center h-8 w-8 rounded bg-red-50 text-red-600">
                                  <span className="material-symbols-outlined text-[20px]">picture_as_pdf</span>
                                </div>
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap">
                                <div className="flex flex-col">
                                  <span className="text-sm font-medium text-[#0d181c]">{doc.filename}</span>
                                  <span className="text-xs text-admin-text-secondary">ID: {doc.document_id.slice(0, 8)}...</span>
                                </div>
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap">
                                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-50 text-blue-700">
                                  {doc.chunks_count} chunks
                                </span>
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap text-sm text-admin-text-secondary">
                                {formatDate(doc.uploaded_at)}
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap">
                                <div className="flex items-center gap-1.5">
                                  <div className="h-2 w-2 rounded-full bg-green-500"></div>
                                  <span className="text-sm text-[#0d181c]">Indicizzato</span>
                                </div>
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                                <button
                                  onClick={() => handleDeleteDoc(doc.document_id)}
                                  className="text-admin-text-secondary hover:text-red-500 transition-colors p-1 rounded hover:bg-red-50"
                                  title="Elimina documento"
                                >
                                  <span className="material-symbols-outlined">delete</span>
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <div className="bg-white px-4 py-3 flex items-center justify-between border-t border-[#cee2e9] sm:px-6">
                      <div className="text-sm text-admin-text-secondary">
                        <span className="font-medium text-[#0d181c]">{documents.length}</span> documenti
                      </div>
                    </div>
                  </>
                )}
              </div>
            ) : (
              /* ═══ KNOWLEDGE LIST (Cards) ═══ */
              <>
                {loadingKB ? (
                  <div className="flex items-center justify-center py-20">
                    <div className="flex flex-col items-center gap-3">
                      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-admin-primary"></div>
                      <span className="text-admin-text-secondary text-sm">Caricamento knowledge...</span>
                    </div>
                  </div>
                ) : filteredKnowledges.length === 0 ? (
                  <div className="bg-white rounded-xl border border-[#cee2e9] shadow-sm flex flex-col items-center justify-center py-20 text-center">
                    <span className="material-symbols-outlined text-[48px] text-admin-text-secondary mb-4">auto_stories</span>
                    <h3 className="text-lg font-semibold text-[#0d181c] mb-2">
                      {knowledges.length === 0 ? 'Nessuna Knowledge Base' : 'Nessun risultato'}
                    </h3>
                    <p className="text-admin-text-secondary text-sm max-w-md">
                      {knowledges.length === 0
                        ? 'Crea la tua prima Knowledge Base per iniziare a organizzare i documenti.'
                        : 'Nessuna knowledge corrisponde alla tua ricerca.'}
                    </p>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {filteredKnowledges.map((kb) => (
                      <div
                        key={kb.id}
                        onClick={() => handleSelectKB(kb)}
                        className="bg-white rounded-xl border border-[#cee2e9] shadow-sm p-6 cursor-pointer hover:shadow-md hover:border-admin-primary/40 transition-all group"
                      >
                        <div className="flex items-start justify-between mb-4">
                          <div className="flex items-center gap-3">
                            <div className="flex items-center justify-center h-10 w-10 rounded-lg bg-admin-primary/10 text-admin-primary">
                              <span className="material-symbols-outlined text-[24px]">auto_stories</span>
                            </div>
                            <div>
                              <h3 className="text-sm font-bold text-[#0d181c] group-hover:text-admin-primary transition-colors">
                                {kb.name}
                              </h3>
                              <p className="text-xs text-admin-text-secondary">{formatDate(kb.created_at)}</p>
                            </div>
                          </div>
                          <button
                            onClick={(e) => handleDeleteKB(kb.id, e)}
                            className="text-admin-text-secondary hover:text-red-500 transition-colors p-1 rounded hover:bg-red-50 opacity-0 group-hover:opacity-100"
                            title="Elimina knowledge"
                          >
                            <span className="material-symbols-outlined text-[20px]">delete</span>
                          </button>
                        </div>
                        {kb.description && (
                          <p className="text-sm text-admin-text-secondary mb-4 line-clamp-2">{kb.description}</p>
                        )}
                        <div className="flex items-center gap-4 pt-3 border-t border-[#cee2e9]">
                          <div className="flex items-center gap-1.5">
                            <span className="material-symbols-outlined text-admin-text-secondary text-[16px]">description</span>
                            <span className="text-xs font-medium text-[#0d181c]">{kb.documents_count} documenti</span>
                          </div>
                          <div className="flex items-center gap-1.5">
                            <div className="h-1.5 w-1.5 rounded-full bg-green-500"></div>
                            <span className="text-xs text-admin-text-secondary">Attiva</span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </main>

      {/* ─── Create Knowledge Modal ─── */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl max-w-md w-full p-6">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-lg font-bold text-[#0d181c]">Nuova Knowledge Base</h3>
              <button onClick={() => setShowCreateModal(false)} className="p-1 rounded-lg hover:bg-gray-100 transition-colors">
                <span className="material-symbols-outlined text-admin-text-secondary">close</span>
              </button>
            </div>
            <div className="flex flex-col gap-4">
              <div>
                <label className="block text-sm font-medium text-[#0d181c] mb-1">Nome *</label>
                <input
                  value={newKBName}
                  onChange={(e) => setNewKBName(e.target.value)}
                  placeholder="Es. Documenti 2025"
                  className="w-full px-3 py-2.5 rounded-lg border border-[#cee2e9] text-sm focus:outline-none focus:ring-2 focus:ring-admin-primary"
                  autoFocus
                  onKeyDown={(e) => e.key === 'Enter' && handleCreateKB()}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-[#0d181c] mb-1">Descrizione</label>
                <textarea
                  value={newKBDesc}
                  onChange={(e) => setNewKBDesc(e.target.value)}
                  placeholder="Descrizione opzionale..."
                  rows={3}
                  className="w-full px-3 py-2.5 rounded-lg border border-[#cee2e9] text-sm focus:outline-none focus:ring-2 focus:ring-admin-primary resize-none"
                />
              </div>
            </div>
            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => setShowCreateModal(false)}
                className="px-4 py-2 rounded-lg border border-[#cee2e9] text-sm font-medium hover:bg-gray-50 transition-colors"
              >
                Annulla
              </button>
              <button
                onClick={handleCreateKB}
                disabled={!newKBName.trim() || creating}
                className="px-4 py-2 rounded-lg bg-admin-primary text-white text-sm font-semibold hover:brightness-95 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {creating ? 'Creazione...' : 'Crea Knowledge'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default KnowledgeBase;
