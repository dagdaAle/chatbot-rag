import { useEffect, useState, type FormEvent, type ReactNode } from 'react';
import type { Session } from '@supabase/supabase-js';
import { AuthContext } from './AuthContext';
import { supabase } from './supabase';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { api, type Profile } from '@/api/admin';
import { PasswordForm } from '@/components/settings/AccountPage';
import { Toaster } from '@/components/ui/sonner';
import intechaLogo from '@/assets/intecha-logo-white.svg';

function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      const result = await supabase.auth.signInWithPassword({ email: email.trim(), password });
      if (result.error) setError('Accesso non riuscito. Verifica email e password.');
    } catch {
      setError('Servizio non raggiungibile. Riprova tra poco.');
    } finally {
      setPassword('');
      setBusy(false);
    }
  }
  return <main className="bg-background flex min-h-screen items-center justify-center p-6">
    <form onSubmit={submit} className="w-full max-w-sm overflow-hidden rounded-xl border shadow-sm">
      <div className="bg-[#0E1116] px-6 py-6">
        <img src={intechaLogo} alt="Intecha" width={179} height={30} className="h-[30px] w-auto" />
      </div>
      <div className="space-y-5 p-6">
      <div><h1 className="text-xl font-semibold">Accedi a Chatbot RAG</h1>
        <p className="text-muted-foreground mt-2 text-sm">Accesso riservato agli utenti invitati.</p></div>
      <div className="space-y-2"><Label htmlFor="email">Email</Label>
        <Input id="email" type="email" autoComplete="username" value={email} onChange={e => setEmail(e.target.value)} required disabled={busy} /></div>
      <div className="space-y-2"><Label htmlFor="password">Password</Label>
        <Input id="password" type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required disabled={busy} /></div>
      {error && <p role="alert" className="text-destructive text-sm">{error}</p>}
      <Button type="submit" className="w-full" disabled={busy}>{busy ? 'Accesso…' : 'Accedi'}</Button>
      </div>
    </form>
  </main>;
}

export function AuthGate({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let alive = true;
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, next) => {
      if (alive) { setSession(next); setLoading(false); }
    });
    // Supabase emits INITIAL_SESSION after loading persisted state.
    return () => { alive = false; subscription.unsubscribe(); };
  }, []);
  if (loading) return <main className="flex min-h-screen items-center justify-center" role="status">Caricamento sessione…</main>;
  if (!session) return <Login />;
  return <ProfileGate key={session.user.id} session={session}>{children}</ProfileGate>;
}

function ProfileGate({ session, children }: { session: Session; children: ReactNode }) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let alive = true;
    const load = () => api<Profile>('account/me').then(p => { if (alive) { setProfile(p); setError(''); } }).catch(err => { if (alive) { setProfile(null); setError(err.message); } });
    load(); const timer = setInterval(load, 60000); window.addEventListener('focus', load);
    return () => { alive = false; clearInterval(timer); window.removeEventListener('focus', load); };
  }, [retry]);
  if (!profile) return <main className="space-y-4 p-8"><p role="status">{error || 'Verifica account…'}</p>{error && <Button onClick={() => setRetry(v => v + 1)}>Riprova</Button>}<Button variant="outline" onClick={() => supabase.auth.signOut({ scope: 'local' })}>Esci</Button></main>;
  const user = { ...session.user, app_metadata: { ...session.user.app_metadata, chatbot_role: profile.role } };
  return <AuthContext.Provider value={user}>{profile.must_change_password ? <main className="mx-auto max-w-lg space-y-6 p-8"><h1 className="text-xl font-semibold">Imposta la tua password personale</h1><PasswordForm onChanged={() => setRetry(v => v + 1)} /><Button variant="outline" onClick={() => supabase.auth.signOut({scope:'local'})}>Esci</Button><Toaster /></main> : children}</AuthContext.Provider>;
}
