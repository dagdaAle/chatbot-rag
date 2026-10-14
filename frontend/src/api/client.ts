import { authFetch } from '@/auth/supabase';
/** Client API backend - URL da variabile ambiente in build-time */
const API_URL = import.meta.env.VITE_API_URL || '';

/** Una sola gestione errori per tutte le chiamate: il messaggio arriva dal backend. */
async function request<T>(path: string, init: RequestInit & { json?: unknown } = {}, fallback = 'Operazione non riuscita'): Promise<T> {
  const { json, ...rest } = init;
  const res = await authFetch(`${API_URL}${path}`, json === undefined ? rest : {
    ...rest, headers: { 'Content-Type': 'application/json', ...rest.headers }, body: JSON.stringify(json),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(typeof err.detail === 'string' ? err.detail : fallback);
  }
  return res.json();
}

export async function fetchHealth(): Promise<{ status: string }> {
  return request(`/health`, {}, 'Health check failed');
}

export async function fetchHealthQdrant(): Promise<{
  status: string;
  qdrant: string;
  collections_count: number;
}> {
  return request(`/health/qdrant`, {}, 'Qdrant health check failed');
}

// ============ Knowledge API ============

export type KnowledgeVisibility = 'private' | 'organization';
export type KnowledgePermission = 'owner' | 'editor' | 'viewer';

export interface KnowledgeItem {
  id: string;
  name: string;
  description: string;
  created_at: string;
  documents_count: number;
  owner_user_id: string;
  visibility: KnowledgeVisibility;
  /** Calcolati dal database: il frontend non ricalcola i permessi. */
  permission: KnowledgePermission | null;
  can_edit: boolean;
  can_own: boolean;
}

export interface KnowledgeListResponse {
  knowledges: KnowledgeItem[];
  total: number;
}

export interface KnowledgeMember {
  user_id: string;
  role: 'editor' | 'viewer';
}

export interface KnowledgeAccess {
  visibility: KnowledgeVisibility;
  owner_user_id: string;
  members: KnowledgeMember[];
}

export interface DirectoryUser {
  id: string;
  email: string;
  display_name: string;
  role: 'admin' | 'member' | 'viewer';
}

export async function fetchKnowledges(): Promise<KnowledgeListResponse> {
  return request(`/api/knowledge`, {}, 'Errore caricamento knowledge');
}

export async function createKnowledge(name: string, description = '', visibility: KnowledgeVisibility = 'private'): Promise<KnowledgeItem> {
  return request(`/api/knowledge`, { method: 'POST', json: { name, description, visibility } });
}

export async function updateKnowledge(knowledgeId: string, name: string, description: string): Promise<KnowledgeItem> {
  return request(`/api/knowledge/${knowledgeId}`, { method: 'PUT', json: { name, description } });
}

export async function deleteKnowledge(knowledgeId: string): Promise<{ id: string; status: string }> {
  return request(`/api/knowledge/${knowledgeId}`, { method: 'DELETE' }, 'Errore eliminazione knowledge');
}

export async function fetchKnowledgeAccess(knowledgeId: string): Promise<KnowledgeAccess> {
  return request(`/api/knowledge/${knowledgeId}/access`);
}

export async function saveKnowledgeAccess(knowledgeId: string, access: { visibility: KnowledgeVisibility; members: KnowledgeMember[]; owner_user_id?: string }): Promise<{ success: boolean }> {
  return request(`/api/knowledge/${knowledgeId}/access`, { method: 'PUT', json: access });
}

export async function fetchDirectory(): Promise<DirectoryUser[]> {
  return request(`/api/directory`);
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
  return request(`/api/knowledge/${knowledgeId}/documents`, {}, 'Errore caricamento documenti');
}

export async function uploadDocuments(knowledgeId: string, files: File[]): Promise<UploadResult> {
  const formData = new FormData();
  for (const file of files) {
    formData.append('files', file);
  }
  return request(`/api/knowledge/${knowledgeId}/documents/upload`, { method: 'POST', body: formData });
}

export async function deleteDocument(knowledgeId: string, documentId: string): Promise<{ document_id: string; status: string }> {
  return request(`/api/knowledge/${knowledgeId}/documents/${documentId}`, { method: 'DELETE' }, 'Errore eliminazione documento');
}

// ============ Chat API ============

export interface ChatSource {
  knowledge_id?: string | null;
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
 * Compatibilità con URL salvati; le fonti nella chat usano il lettore laterale.
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
  modelKey?: string,
): Promise<ChatResponse> {
  return request(`/api/chat`, { method: 'POST', json: {
      question,
      top_k: topK,
      conversation_history: conversationHistory,
      knowledge_id: knowledgeId || null,
      conversation_id: conversationId || null,
      model_key: modelKey || null,
    } });
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
  return request(`/api/conversations`, {}, 'Errore caricamento conversazioni');
}

export async function createConversation(title: string, knowledgeId?: string): Promise<ConversationItem> {
  return request(`/api/conversations`, { method: 'POST', json: {
      title,
      knowledge_id: knowledgeId || null,
    } });
}

export async function fetchConversation(id: string): Promise<ConversationDetail> {
  return request(`/api/conversations/${id}`, {});
}

export async function deleteConversation(id: string): Promise<{ id: string; status: string }> {
  return request(`/api/conversations/${id}`, { method: 'DELETE' });
}

export async function addMessageToConversation(
  conversationId: string,
  role: 'user' | 'assistant',
  content: string,
  sources?: ChatSource[],
): Promise<ConversationMessage> {
  return request(`/api/conversations/${conversationId}/messages`, { method: 'POST', json: {
      role,
      content,
      sources: sources || null,
    } });
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
  return request(`/api/settings/prompt`, {}, 'Errore caricamento prompt');
}

export async function updateSystemPrompt(prompt: string): Promise<PromptUpdateResponse> {
  return request(`/api/settings/prompt`, { method: 'PUT', json: { prompt } });
}

export async function resetSystemPrompt(): Promise<PromptUpdateResponse> {
  return request(`/api/settings/prompt/reset`, { method: 'POST' }, 'Errore ripristino prompt');
}

export async function fetchDefaultPrompt(): Promise<PromptResponse> {
  return request(`/api/settings/prompt/default`, {}, 'Errore caricamento prompt di default');
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
  chat_provider: string;
  embedding_provider: string;
  chat_model: string;
  embedding_model: string;
  ollama_available: boolean;
  openai_available: boolean;
  deepseek_available: boolean;
}

export async function fetchProviderConfig(): Promise<ProviderConfigResponse> {
  return request(`/api/settings/models/config`, {}, 'Errore caricamento configurazione provider');
}

export async function fetchChatModels(): Promise<ModelsListResponse> {
  return request(`/api/settings/models/chat`, {}, 'Errore caricamento modelli chat');
}

export async function fetchEmbeddingModels(): Promise<ModelsListResponse> {
  return request(`/api/settings/models/embedding`, {}, 'Errore caricamento modelli embedding');
}

export async function setChatModel(modelId: string, provider: string): Promise<ModelSetResponse> {
  return request(`/api/settings/models/chat`, { method: 'PUT', json: { model_id: modelId, provider } });
}

export async function setEmbeddingModel(modelId: string, provider: string): Promise<ModelSetResponse> {
  return request(`/api/settings/models/embedding`, { method: 'PUT', json: { model_id: modelId, provider } });
}
