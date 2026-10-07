import { UsagePanel } from '@/components/admin/AdminPage';
import { useState, type FormEvent } from 'react';
import { toast } from 'sonner';
import { api } from '@/api/admin';
import { useAuthUser } from '@/auth/AuthContext';
import { supabase } from '@/auth/supabase';
import { PageHeader } from '@/components/layout/AppLayout';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
export function PasswordForm({ onChanged }: { onChanged?: () => void }) {
  const [current, setCurrent] = useState(''); const [password, setPassword] = useState(''); const [confirm, setConfirm] = useState(''); const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault(); if (password !== confirm) { toast.error('Le password non coincidono'); return; }
    setBusy(true);
    try { await api('account/password','PUT',{ current_password: current, password }); setCurrent(''); setPassword(''); setConfirm(''); toast.success('Password aggiornata'); await supabase.auth.refreshSession(); onChanged?.(); }
    catch (err) { toast.error((err as Error).message); } finally { setBusy(false); }
  }
  return <form onSubmit={submit} className="max-w-md space-y-4">
    <div className="space-y-2"><Label htmlFor="current-password">Password attuale</Label><Input id="current-password" type="password" autoComplete="current-password" value={current} onChange={e => setCurrent(e.target.value)} required /></div>
    <div className="space-y-2"><Label htmlFor="new-password">Nuova password (almeno 12 caratteri)</Label><Input id="new-password" type="password" autoComplete="new-password" minLength={12} maxLength={128} value={password} onChange={e => setPassword(e.target.value)} required /></div>
    <div className="space-y-2"><Label htmlFor="confirm-password">Ripeti nuova password</Label><Input id="confirm-password" type="password" autoComplete="new-password" value={confirm} onChange={e => setConfirm(e.target.value)} required /></div>
    <Button disabled={busy}>{busy ? 'Aggiornamento…' : 'Cambia password'}</Button>
  </form>;
}
export function AccountPage() {
  const user = useAuthUser();
  return <div className="flex h-full min-h-0 flex-col"><PageHeader title="Il mio account" /><div className="space-y-6 overflow-auto p-6"><p>{user.email}</p><PasswordForm /><h2 className="text-lg font-medium">I miei utilizzi</h2><UsagePanel personal /></div></div>;
}
