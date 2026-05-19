/** Client API backend - URL da variabile ambiente in build-time */
const API_URL = import.meta.env.VITE_API_URL || '';

export async function fetchHealth(): Promise<{ status: string }> {
  const res = await fetch(`${API_URL}/health`);
  if (!res.ok) throw new Error('Health check failed');
  return res.json();
}

export async function fetchHealthQdrant(): Promise<{
  status: string;
  qdrant: string;
  collections_count: number;
}> {
  const res = await fetch(`${API_URL}/health/qdrant`);
  if (!res.ok) throw new Error('Qdrant health check failed');
  return res.json();
}

// ============ Knowledge API ============

export interface KnowledgeItem {
  id: string;
  name: string;
  description: string;
  created_at: string;
  documents_count: number;
}

export interface KnowledgeListResponse {
  knowledges: KnowledgeItem[];
  total: number;
}

export async function fetchKnowledges(): Promise<KnowledgeListResponse> {
  const res = await fetch(`${API_URL}/api/knowledge`);
  if (!res.ok) throw new Error('Errore caricamento knowledge');
  return res.json();
}

export async function createKnowledge(name: string, description: string = ''): Promise<KnowledgeItem> {
  const res = await fetch(`${API_URL}/api/knowledge`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, description }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail));
  }
  return res.json();
}

export async function deleteKnowledge(knowledgeId: string): Promise<{ id: string; status: string }> {
  const res = await fetch(`${API_URL}/api/knowledge/${knowledgeId}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Errore eliminazione knowledge');
  return res.json();
}

// ============ Documents API (per Knowledge) ============

export interface DocumentItem {
  document_id: string;
  filename: string;
  uploaded_at: string;
  chunks_count: number;
}

export interface UploadResult {
  uploaded: {
    document_id: string;
    filename: string;
    chunks_count: number;
    status: string;
  }[];
  errors: {
    filename: string;
    error: string;
  }[];
  total_uploaded: number;
  total_errors: number;
}

export async function fetchDocuments(knowledgeId: string): Promise<{ documents: DocumentItem[]; total: number }> {
  const res = await fetch(`${API_URL}/api/knowledge/${knowledgeId}/documents`);
  if (!res.ok) throw new Error('Errore caricamento documenti');
  return res.json();
}

export async function uploadDocuments(knowledgeId: string, files: File[]): Promise<UploadResult> {
  const formData = new FormData();
  for (const file of files) {
    formData.append('files', file);
  }
  const res = await fetch(`${API_URL}/api/knowledge/${knowledgeId}/documents/upload`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail));
  }
  return res.json();
}

export async function deleteDocument(knowledgeId: string, documentId: string): Promise<{ document_id: string; status: string }> {
  const res = await fetch(`${API_URL}/api/knowledge/${knowledgeId}/documents/${documentId}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Errore eliminazione documento');
  return res.json();
}

// ============ Chat API ============

export interface ChatSource {
  filename: string;
  score: number;
  text: string;
  chunk_index: number;
  document_id: string;
  page_start: number;
  page_end: number;
}

/**
 * Restituisce l'URL backend per scaricare il PDF originale di un documento.
 */
export function getDocumentFileUrl(knowledgeId: string, documentId: string): string {
  return `${API_URL}/api/knowledge/${knowledgeId}/documents/${documentId}/file`;
}

/**
 * Costruisce l'URL del PDF viewer integrato nell'app.
 * Si apre in una nuova tab con il PDF renderizzato, scrollato alla pagina e con testo evidenziato.
 */
export function getPDFViewerUrl(params: {
  knowledgeId: string;
  documentId: string;
  pageStart: number;
  pageEnd?: number;
  text?: string;
  filename?: string;
  score?: number;
}): string {
  const qs = new URLSearchParams();
  qs.set('kb', params.knowledgeId);
  qs.set('doc', params.documentId);
  qs.set('page', String(params.pageStart));
  if (params.pageEnd && params.pageEnd !== params.pageStart) {
    qs.set('pageEnd', String(params.pageEnd));
  }
  if (params.text) qs.set('text', params.text);
  if (params.filename) qs.set('filename', params.filename);
  if (params.score) qs.set('score', String(params.score));
  return `/pdf-viewer?${qs.toString()}`;
}

export interface ChatResponse {
  answer: string;
  sources: ChatSource[];
  contexts_used: number;
  conversation_id?: string | null;
}

export interface ChatMessageItem {
  role: 'user' | 'assistant';
  content: string;
}

export async function sendChatMessage(
  question: string,
  conversationHistory: ChatMessageItem[] = [],
  topK: number = 5,
  knowledgeId?: string,
  conversationId?: string,
): Promise<ChatResponse> {
  const res = await fetch(`${API_URL}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      question,
      top_k: topK,
      conversation_history: conversationHistory,
      knowledge_id: knowledgeId || null,
      conversation_id: conversationId || null,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail));
  }
  return res.json();
}

// ============ Conversations API ============

export interface ConversationItem {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  knowledge_id?: string | null;
}

export interface ConversationListResponse {
  conversations: ConversationItem[];
  total: number;
}

export interface ConversationMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: ChatSource[] | null;
  timestamp?: string | null;
}

export interface ConversationDetail {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  knowledge_id?: string | null;
  messages: ConversationMessage[];
}

export async function fetchConversations(): Promise<ConversationListResponse> {
  const res = await fetch(`${API_URL}/api/conversations`);
  if (!res.ok) throw new Error('Errore caricamento conversazioni');
  return res.json();
}

export async function createConversation(title: string, knowledgeId?: string): Promise<ConversationItem> {
  const res = await fetch(`${API_URL}/api/conversations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      title,
      knowledge_id: knowledgeId || null,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail));
  }
  return res.json();
}

export async function fetchConversation(id: string): Promise<ConversationDetail> {
  const res = await fetch(`${API_URL}/api/conversations/${id}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail));
  }
  return res.json();
}

export async function deleteConversation(id: string): Promise<{ id: string; status: string }> {
  const res = await fetch(`${API_URL}/api/conversations/${id}`, { method: 'DELETE' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail));
  }
  return res.json();
}

export async function addMessageToConversation(
  conversationId: string,
  role: 'user' | 'assistant',
  content: string,
  sources?: ChatSource[],
): Promise<ConversationMessage> {
  const res = await fetch(`${API_URL}/api/conversations/${conversationId}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      role,
      content,
      sources: sources || null,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail));
  }
  return res.json();
}

// ============ Settings API (Prompt) ============

export interface PromptResponse {
  prompt: string;
  is_default: boolean;
}

export interface PromptUpdateResponse {
  success: boolean;
  message: string;
}

export async function fetchSystemPrompt(): Promise<PromptResponse> {
  const res = await fetch(`${API_URL}/api/settings/prompt`);
  if (!res.ok) throw new Error('Errore caricamento prompt');
  return res.json();
}

export async function updateSystemPrompt(prompt: string): Promise<PromptUpdateResponse> {
  const res = await fetch(`${API_URL}/api/settings/prompt`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail));
  }
  return res.json();
}

export async function resetSystemPrompt(): Promise<PromptUpdateResponse> {
  const res = await fetch(`${API_URL}/api/settings/prompt/reset`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error('Errore ripristino prompt');
  return res.json();
}

export async function fetchDefaultPrompt(): Promise<PromptResponse> {
  const res = await fetch(`${API_URL}/api/settings/prompt/default`);
  if (!res.ok) throw new Error('Errore caricamento prompt di default');
  return res.json();
}

// ============ Models API ============

export interface ModelInfo {
  id: string;
  name: string;
  provider: string;
}

export interface ModelsListResponse {
  models: ModelInfo[];
  current: string;
  provider: string;
}

export interface ModelSetRequest {
  model_id: string;
  provider: string;
}

export interface ModelSetResponse {
  success: boolean;
  model_id: string;
  provider: string;
  message: string;
}

export interface ProviderConfigResponse {
  llm_provider: string;
  chat_model: string;
  embedding_model: string;
  ollama_available: boolean;
  openai_available: boolean;
}

export async function fetchProviderConfig(): Promise<ProviderConfigResponse> {
  const res = await fetch(`${API_URL}/api/settings/models/config`);
  if (!res.ok) throw new Error('Errore caricamento configurazione provider');
  return res.json();
}

export async function fetchChatModels(): Promise<ModelsListResponse> {
  const res = await fetch(`${API_URL}/api/settings/models/chat`);
  if (!res.ok) throw new Error('Errore caricamento modelli chat');
  return res.json();
}

export async function fetchEmbeddingModels(): Promise<ModelsListResponse> {
  const res = await fetch(`${API_URL}/api/settings/models/embedding`);
  if (!res.ok) throw new Error('Errore caricamento modelli embedding');
  return res.json();
}

export async function setChatModel(modelId: string, provider: string): Promise<ModelSetResponse> {
  const res = await fetch(`${API_URL}/api/settings/models/chat`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model_id: modelId, provider }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail));
  }
  return res.json();
}

export async function setEmbeddingModel(modelId: string, provider: string): Promise<ModelSetResponse> {
  const res = await fetch(`${API_URL}/api/settings/models/embedding`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model_id: modelId, provider }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail));
  }
  return res.json();
}
