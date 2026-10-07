import { authFetch } from '@/auth/supabase';
export const apiBase = import.meta.env.VITE_API_URL || '';
export async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const res = await authFetch(`${apiBase}/api/${path}`, { method, headers: body === undefined ? undefined : { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
  if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error(typeof err.detail === 'string' ? err.detail : 'Operazione non riuscita'); }
  return res.json();
}
export interface Profile {
  id: string; email: string; display_name: string; role: 'admin' | 'manager' | 'user'; active: boolean;
  must_change_password: boolean; monthly_requests: number | null; requests_per_minute: number;
  concurrent_requests: number; created_at: string;
}
export interface Member { user_id: string; can_manage?: boolean; knowledge_id?: string; model_key?: string }
export interface AdminKnowledge { id: string; name: string; shared: boolean; created_by: string | null; documents: { count: number; size_bytes?: number }[] }
export interface AdminModel { key: string; provider: 'openai' | 'deepseek' | 'ollama'; model_id: string; kind: 'chat' | 'embedding'; name: string; enabled: boolean; shared: boolean; input_per_million: number | null; output_per_million: number | null; currency: string }
export interface UsageGroup { user_id: string; provider: string; model_id: string; operation: string; calls: number; errors: number; input_tokens: number; output_tokens: number; unknown_tokens: number; duration_ms: number }
export interface UsageEvent { id: string; user_id: string; created_at: string; provider: string; model_id: string; operation: string; status: string; duration_ms: number; estimated_cost: number | null; currency: string | null }
export interface UsageData { groups: UsageGroup[]; costs: Record<string, number>; total_events: number; events: UsageEvent[]; unknown_cost_events: number }
export interface AuditEntry { id: number; actor_id: string; action: string; target: string; created_at: string }
