import { createClient } from '@supabase/supabase-js';

// Publishable key, never a service-role or sb_secret key.
const url = import.meta.env.VITE_SUPABASE_URL || 'https://supabase.intecha.dev';
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY || 'sb_publishable_eOn6jCKOJYVPzRh39CQIFJ_0zYEU4iV';
export const supabase = createClient(url, key, {
  auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: false },
});

export async function authFetch(input: RequestInfo | URL, init: RequestInit = {}) {
  const { data, error } = await supabase.auth.getSession();
  if (error || !data.session) throw new Error('Accedi per continuare');
  const userId = data.session.user.id;
  const headers = new Headers(init.headers);
  headers.set('Authorization', `Bearer ${data.session.access_token}`);
  const response = await fetch(input, { ...init, headers });
  const current = (await supabase.auth.getSession()).data.session;
  // Do not deliver a previous account's delayed response after logout/account switch.
  if (current?.user.id !== userId) throw new Error('Sessione cambiata');
  if (response.status === 401) {
    await supabase.auth.signOut({ scope: 'local' });
    throw new Error('Sessione scaduta. Accedi nuovamente.');
  }
  return response;
}
