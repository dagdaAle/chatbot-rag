import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Navigate } from 'react-router-dom';
import { toast } from 'sonner';
import { useAuthUser } from '@/auth/AuthContext';
import { api, apiBase, type Profile, type AdminKnowledge, type AdminModel, type Member, type UsageData, type AuditEntry } from '@/api/admin';
import { authFetch } from '@/auth/supabase';
import { PageHeader } from '@/components/layout/AppLayout';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

const selectClass = 'border-input bg-background h-9 rounded-md border px-3 text-sm';
const roleName = { admin: 'Amministratore', manager: 'Gestore KB', user: 'Utente' };
function ErrorBox({ error }: { error: string }) { return error ? <p role="alert" className="text-destructive rounded-md border p-3 text-sm">{error}</p> : null; }
function Check({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) {
  return <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)} />{label}</label>;
}
function Field({ label, children }: { label: string; children: React.ReactNode }) { return <label className="grid gap-2 text-sm">{label}{children}</label>; }

function UserEditor({ user, onSaved }: { user: Profile; onSaved: () => void }) {
  const [draft, setDraft] = useState(user); const [email, setEmail] = useState(user.email);
  const [password, setPassword] = useState(''); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  async function run(action: () => Promise<unknown>, message: string) {
    setBusy(true); setError('');
    try { await action(); toast.success(message); onSaved(); } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }
  return <div className="space-y-6">
    <form className="space-y-4" onSubmit={e => { e.preventDefault(); run(() => api(`admin/users/${user.id}`, 'PUT', draft), 'Permessi aggiornati'); }}>
      <Field label="Nome"><Input value={draft.display_name} onChange={e => setDraft({ ...draft, display_name: e.target.value })} maxLength={200} /></Field>
      <Field label="Ruolo"><select className={selectClass} value={draft.role} onChange={e => setDraft({ ...draft, role: e.target.value as Profile['role'] })}>{Object.entries(roleName).map(([key, name]) => <option key={key} value={key}>{name}</option>)}</select></Field>
      <Check label="Account attivo" checked={draft.active} onChange={active => setDraft({ ...draft, active })} />
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Richieste/mese"><Input type="number" min={1} placeholder="Illimitate" value={draft.monthly_requests ?? ''} onChange={e => setDraft({ ...draft, monthly_requests: e.target.value ? Number(e.target.value) : null })} /></Field>
        <Field label="Richieste/minuto"><Input type="number" min={1} max={600} value={draft.requests_per_minute} onChange={e => setDraft({ ...draft, requests_per_minute: Number(e.target.value) })} /></Field>
        <Field label="Richieste simultanee"><Input type="number" min={1} max={20} value={draft.concurrent_requests} onChange={e => setDraft({ ...draft, concurrent_requests: Number(e.target.value) })} /></Field>
      </div>
      <Button disabled={busy}>Salva profilo e permessi</Button>
    </form>
    <form className="space-y-3 border-t pt-4" onSubmit={e => { e.preventDefault(); run(() => api(`admin/users/${user.id}/email`, 'PUT', { email }), 'Email aggiornata'); }}>
      <Field label="Email di accesso"><Input type="email" required value={email} onChange={e => setEmail(e.target.value)} /></Field><Button variant="outline" disabled={busy}>Aggiorna email</Button>
    </form>
    <form className="space-y-3 border-t pt-4" onSubmit={e => { e.preventDefault(); run(async () => { await api(`admin/users/${user.id}/password`, 'PUT', { password }); setPassword(''); }, 'Password temporanea impostata'); }}>
      <Field label="Nuova password temporanea"><Input type="password" autoComplete="new-password" required minLength={12} maxLength={128} value={password} onChange={e => setPassword(e.target.value)} /></Field>
      <p className="text-muted-foreground text-xs">L’utente dovrà impostare una password personale prima di usare l’app.</p>
      <Button variant="outline" disabled={busy}>Reimposta password</Button>
    </form>
    <Button variant="outline" disabled={busy} onClick={() => run(() => api(`admin/users/${user.id}/revoke-sessions`, 'POST'), 'Sessioni revocate: sarà necessario accedere nuovamente')}>Revoca tutte le sessioni</Button>
    <ErrorBox error={error} />
  </div>;
}
function CreateUserForm({ onSaved }: { onSaved: () => void }) {
  const [email, setEmail] = useState(''); const [name, setName] = useState(''); const [password, setPassword] = useState(''); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError('');
    try { await api('admin/users', 'POST', { email, display_name: name, password }); setPassword(''); toast.success('Utente creato: comunica la password temporanea attraverso un canale riservato'); onSaved(); }
    catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }
  return <form className="space-y-4" onSubmit={submit}><Field label="Nome"><Input value={name} onChange={e => setName(e.target.value)} /></Field><Field label="Email"><Input type="email" required value={email} onChange={e => setEmail(e.target.value)} /></Field><Field label="Password temporanea (almeno 12 caratteri)"><Input type="password" autoComplete="new-password" minLength={12} maxLength={128} required value={password} onChange={e => setPassword(e.target.value)} /></Field><p className="text-muted-foreground text-xs">Creazione diretta senza invio email. Il cambio password al primo accesso è obbligatorio.</p><ErrorBox error={error} /><Button disabled={busy}>Crea utente</Button></form>;
}
function Members({ users, members, setMembers, manage = false }: { users: Profile[]; members: Member[]; setMembers: (value: Member[]) => void; manage?: boolean }) {
  return <div className="max-h-56 space-y-3 overflow-auto rounded-md border p-3">{users.filter(u => u.role !== 'admin').map(user => {
    const member = members.find(m => m.user_id === user.id);
    return <div key={user.id} className="flex flex-wrap items-center justify-between gap-2"><Check label={`${user.display_name || user.email}${!user.active ? ' (sospeso)' : ''}`} checked={!!member} onChange={checked => setMembers(checked ? [...members, { user_id: user.id, can_manage: false }] : members.filter(m => m.user_id !== user.id))} />
      {manage && member && user.role === 'manager' && <Check label="Gestisce documenti" checked={!!member.can_manage} onChange={can_manage => setMembers(members.map(m => m.user_id === user.id ? { ...m, can_manage } : m))} />}</div>;
  })}</div>;
}
function KnowledgeEditor({ kb, users, initial, onSaved }: { kb: AdminKnowledge; users: Profile[]; initial: Member[]; onSaved: () => void }) {
  const [shared, setShared] = useState(kb.shared); const [members, setMembers] = useState(initial); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  return <form className="space-y-4" onSubmit={async e => { e.preventDefault(); setBusy(true); setError(''); try { await api(`admin/knowledge/${kb.id}/access`, 'PUT', { shared, members }); toast.success('Accessi aggiornati'); onSaved(); } catch (err) { setError((err as Error).message); } finally { setBusy(false); } }}>
    <Check label="Visibile a tutti gli utenti attivi" checked={shared} onChange={setShared} />
    <p className="text-muted-foreground text-xs">Gli amministratori accedono sempre. Assegna gli utenti quando la KB è riservata; abilita la gestione documenti per i gestori.</p>
    <Members users={users} members={members} setMembers={setMembers} manage /><ErrorBox error={error} /><Button disabled={busy}>Salva accessi</Button>
  </form>;
}
function ModelEditor({ model, users, initial, onSaved }: { model?: AdminModel; users: Profile[]; initial: Member[]; onSaved: () => void }) {
  const [draft, setDraft] = useState<AdminModel>(model || { key: '', provider: 'ollama', model_id: '', kind: 'chat', name: '', enabled: true, shared: true, input_per_million: null, output_per_million: null, currency: 'USD' });
  const [members, setMembers] = useState(initial); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  return <form className="space-y-4" onSubmit={async e => { e.preventDefault(); setBusy(true); setError(''); try { await api('admin/models', 'PUT', { ...draft, members }); toast.success('Modello aggiornato'); onSaved(); } catch (err) { setError((err as Error).message); } finally { setBusy(false); } }}>
    <Field label="Nome"><Input required value={draft.name} onChange={e => setDraft({ ...draft, name: e.target.value })} /></Field>
    <Field label="Provider"><select disabled={!!model} className={selectClass} value={draft.provider} onChange={e => setDraft({ ...draft, provider: e.target.value as AdminModel['provider'] })}><option value="ollama">Ollama</option><option value="openai">OpenAI</option><option value="deepseek">DeepSeek</option></select></Field>
    <Field label="Tipo"><select className={selectClass} value={draft.kind} onChange={e => setDraft({ ...draft, kind: e.target.value as AdminModel['kind'] })}><option value="chat">Chat</option><option value="embedding">Embedding (tariffe)</option></select></Field>
    <Field label="Identificativo modello"><Input required disabled={!!model} value={draft.model_id} onChange={e => setDraft({ ...draft, model_id: e.target.value })} /></Field>
    <Check label="Abilitato" checked={draft.enabled} onChange={enabled => setDraft({ ...draft, enabled })} /><Check label="Consentito a tutti" checked={draft.shared} onChange={shared => setDraft({ ...draft, shared })} />
    {!draft.shared && <Members users={users} members={members} setMembers={setMembers} />}
    <div className="grid gap-3 sm:grid-cols-2"><Field label="Costo input / milione token"><Input type="number" min={0} step="any" placeholder="Non disponibile" value={draft.input_per_million ?? ''} onChange={e => setDraft({ ...draft, input_per_million: e.target.value ? Number(e.target.value) : null })} /></Field><Field label="Costo output / milione token"><Input type="number" min={0} step="any" placeholder="Non disponibile" value={draft.output_per_million ?? ''} onChange={e => setDraft({ ...draft, output_per_million: e.target.value ? Number(e.target.value) : null })} /></Field></div>
    <Field label="Valuta"><select className={selectClass} value={draft.currency} onChange={e => setDraft({ ...draft, currency: e.target.value })}><option>USD</option><option>EUR</option></select></Field>
    <p className="text-muted-foreground text-xs">Tariffe inserite dall’amministratore. I costi sono stime; gli eventi conservano le tariffe applicate. Modelli embedding possono essere registrati qui per le tariffe, e vengono esclusi dal selettore chat.</p>
    <ErrorBox error={error} /><Button disabled={busy}>Salva modello</Button>
  </form>;
}

export function UsagePanel({ users = [], personal = false }: { users?: Profile[]; personal?: boolean }) {
  const [days, setDays] = useState('30'); const [userId, setUserId] = useState(''); const [model, setModel] = useState(''); const [provider, setProvider] = useState(''); const [offset, setOffset] = useState(0);
  const [data, setData] = useState<UsageData | null>(null); const [error, setError] = useState(''); const [loading, setLoading] = useState(false);
  const params = new URLSearchParams({ days, offset: String(offset), ...(userId ? { user_id: userId } : {}), ...(model ? { model } : {}), ...(provider ? { provider } : {}) }).toString();
  const path = `${personal ? 'account' : 'admin'}/usage?${params}`;
  // eslint-disable-next-line react-hooks/set-state-in-effect -- start loading on external query changes
  useEffect(() => { let alive = true; setLoading(true); api<UsageData>(path).then(value => { if (alive) { setData(value); setError(''); } }).catch(err => { if (alive) setError(err.message); }).finally(() => { if (alive) setLoading(false); }); return () => { alive = false; }; }, [path]);
  const name = (id: string) => users.find(u => u.id === id)?.email || id || 'Utente rimosso';
  async function download() {
    try { const res = await authFetch(`${apiBase}/api/${path}&export=true`); if (!res.ok) throw new Error('Esportazione non riuscita'); const url = URL.createObjectURL(await res.blob()); const link = document.createElement('a'); link.href = url; link.download = 'utilizzi.csv'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); } catch (err) { toast.error((err as Error).message); }
  }
  return <div className="space-y-5">
    <div className="flex flex-wrap items-end gap-3"><Field label="Periodo"><select className={selectClass} value={days} onChange={e => { setDays(e.target.value); setOffset(0); }}><option value="7">Ultimi 7 giorni</option><option value="30">Ultimi 30 giorni</option><option value="90">Ultimi 90 giorni</option><option value="366">Ultimo anno</option></select></Field>
      {!personal && <Field label="Utente"><select className={selectClass} value={userId} onChange={e => { setUserId(e.target.value); setOffset(0); }}><option value="">Tutti</option>{users.map(u => <option key={u.id} value={u.id}>{u.email}</option>)}</select></Field>}
      <Field label="Provider"><select className={selectClass} value={provider} onChange={e => { setProvider(e.target.value); setOffset(0); }}><option value="">Tutti</option><option value="openai">OpenAI</option><option value="deepseek">DeepSeek</option><option value="ollama">Ollama</option></select></Field>
      <Field label="Modello esatto"><Input value={model} onChange={e => { setModel(e.target.value); setOffset(0); }} placeholder="Tutti" /></Field><Button variant="outline" onClick={download} disabled={loading}>Esporta CSV</Button>
    </div>
    <ErrorBox error={error} />{loading && <p role="status">Caricamento utilizzi…</p>}
    {!loading && data && <>
      <div className="grid gap-3 sm:grid-cols-3"><div className="rounded-lg border p-4"><p className="text-muted-foreground text-sm">Richieste chat</p><p className="text-2xl font-semibold">{data.groups.filter(g => g.operation === 'request').reduce((n, g) => n + g.calls, 0)}</p></div><div className="rounded-lg border p-4"><p className="text-muted-foreground text-sm">Costi stimati disponibili</p>{Object.entries(data.costs).map(([currency, cost]) => <p key={currency} className="text-xl">{cost.toFixed(4)} {currency}</p>)}{!Object.keys(data.costs).length && <p>Non disponibili</p>}</div><div className="rounded-lg border p-4"><p className="text-muted-foreground text-sm">Chiamate senza costo stimabile</p><p className="text-2xl font-semibold">{data.unknown_cost_events}</p></div></div>
      <p className="text-muted-foreground text-xs">I dati iniziano dall’attivazione del monitoraggio. Token e costi mancanti non valgono zero. Le richieste includono errori e risposte senza contesto; chat ed embedding sono conteggiati separatamente.</p>
      <div className="overflow-auto"><table className="w-full text-left text-sm"><thead><tr className="border-b">{['Utente', 'Modello / operazione', 'Chiamate', 'Errori', 'Token input', 'Token output', 'Media ms'].map(h => <th className="p-2" key={h}>{h}</th>)}</tr></thead><tbody>{data.groups.map((g, i) => <tr className="border-b" key={i}><td className="p-2">{name(g.user_id)}</td><td className="p-2">{g.provider} {g.model_id || '—'}<p className="text-muted-foreground text-xs">{g.operation}</p></td><td className="p-2">{g.calls}</td><td className="p-2">{g.errors}</td><td className="p-2">{g.operation === 'request' ? '—' : `${g.input_tokens.toLocaleString()}${g.unknown_tokens ? ' + N/D' : ''}`}</td><td className="p-2">{g.operation === 'request' ? '—' : `${g.output_tokens.toLocaleString()}${g.unknown_tokens ? ' + N/D' : ''}`}</td><td className="p-2">{Math.round(g.duration_ms / g.calls)}</td></tr>)}</tbody></table></div>
      {!data.groups.length && <p className="text-muted-foreground">Nessun utilizzo nel periodo selezionato.</p>}
      <h3 className="font-medium">Dettaglio eventi</h3><div className="overflow-auto"><table className="w-full text-left text-sm"><thead><tr><th className="p-2">Data</th><th className="p-2">Utente</th><th className="p-2">Operazione / modello</th><th className="p-2">Esito</th></tr></thead><tbody>{data.events.map(event => <tr className="border-t" key={event.id}><td className="p-2">{new Date(event.created_at).toLocaleString('it-IT')}</td><td className="p-2">{name(event.user_id)}</td><td className="p-2">{event.operation} · {event.model_id}</td><td className="p-2">{event.status}</td></tr>)}</tbody></table></div>
      <div className="flex items-center gap-3"><Button variant="outline" disabled={!offset} onClick={() => setOffset(v => Math.max(0, v - 100))}>Precedenti</Button><span className="text-xs">{Math.min(offset + 1, data.total_events)}–{Math.min(offset + 100, data.total_events)} di {data.total_events}</span><Button variant="outline" disabled={offset + 100 >= data.total_events} onClick={() => setOffset(v => v + 100)}>Successivi</Button></div>
    </>}
  </div>;
}

export function AdminPage() {
  const user = useAuthUser();
  if (user.app_metadata.chatbot_role !== 'admin') return <Navigate to="/" replace />;
  return <AdminContent />;
}
function AdminContent() {
  const [users, setUsers] = useState<Profile[]>([]); const [knowledge, setKnowledge] = useState<AdminKnowledge[]>([]); const [models, setModels] = useState<AdminModel[]>([]);
  const [kbMembers, setKbMembers] = useState<Member[]>([]); const [modelMembers, setModelMembers] = useState<Member[]>([]); const [audit, setAudit] = useState<AuditEntry[]>([]); const [auditOffset, setAuditOffset] = useState(0);
  const [error, setError] = useState(''); const [loading, setLoading] = useState(true); const [filter, setFilter] = useState('');
  const [editor, setEditor] = useState<{ kind: 'user' | 'create-user' | 'knowledge' | 'model'; id?: string } | null>(null);
  const reload = useCallback(async () => {
    setLoading(true); setError('');
    const results = await Promise.allSettled([api<Profile[]>('admin/users'), api<{ knowledge: AdminKnowledge[]; members: Member[] }>('admin/knowledge'), api<{ models: AdminModel[]; members: Member[] }>('admin/models')]);
    const [u, k, m] = results;
    if (u.status === 'fulfilled') setUsers(u.value); if (k.status === 'fulfilled') { setKnowledge(k.value.knowledge); setKbMembers(k.value.members); } if (m.status === 'fulfilled') { setModels(m.value.models); setModelMembers(m.value.members); }
    const failures = results.flatMap(r => r.status === 'rejected' ? [r.reason.message] : []); setError(failures.join(' · ')); setLoading(false);
  }, []);
  // eslint-disable-next-line react-hooks/set-state-in-effect -- initial fetch of administrative data
  useEffect(() => { reload(); }, [reload]);
  useEffect(() => { let alive = true; api<AuditEntry[]>(`admin/audit?offset=${auditOffset}`).then(rows => { if (alive) setAudit(rows); }).catch(err => { if (alive) setError(err.message); }); return () => { alive = false; }; }, [auditOffset, loading]);
  const saved = () => { setEditor(null); reload(); };
  return <div className="flex h-full min-h-0 flex-col"><PageHeader title="Amministrazione"><Button variant="outline" size="sm" disabled={loading} onClick={reload}>Aggiorna</Button></PageHeader><div className="min-h-0 flex-1 space-y-5 overflow-auto p-4 md:p-6">
    <ErrorBox error={error} />{loading && <p role="status">Caricamento amministrazione…</p>}
    <Tabs defaultValue="users"><TabsList className="h-auto flex-wrap"><TabsTrigger value="users">Utenti</TabsTrigger><TabsTrigger value="knowledge">Knowledge base</TabsTrigger><TabsTrigger value="models">Modelli e tariffe</TabsTrigger><TabsTrigger value="usage">Utilizzi</TabsTrigger><TabsTrigger value="audit">Registro attività</TabsTrigger></TabsList>
      <TabsContent value="users" className="space-y-4"><div className="flex gap-3"><Input aria-label="Cerca utenti" placeholder="Cerca nome o email" value={filter} onChange={e => setFilter(e.target.value)} /><Button onClick={() => setEditor({ kind: 'create-user' })}>Nuovo utente</Button></div>
        <div className="overflow-auto"><table className="w-full text-left text-sm"><thead><tr>{['Utente', 'Ruolo', 'Stato', 'Limite mensile', ''].map((h, i) => <th className="p-3" key={i}>{h}</th>)}</tr></thead><tbody>{users.filter(u => `${u.display_name} ${u.email}`.toLowerCase().includes(filter.toLowerCase())).map(u => <tr key={u.id} className="border-t"><td className="p-3">{u.display_name || u.email}<p className="text-muted-foreground text-xs">{u.email}</p></td><td className="p-3">{roleName[u.role]}</td><td className="p-3">{!u.active ? 'Sospeso' : u.must_change_password ? 'Cambio password richiesto' : 'Attivo'}</td><td className="p-3">{u.monthly_requests ?? 'Illimitato'}</td><td className="p-3"><Button variant="outline" size="sm" onClick={() => setEditor({ kind: 'user', id: u.id })}>Gestisci</Button></td></tr>)}</tbody></table></div>
      </TabsContent>
      <TabsContent value="knowledge" className="space-y-3">{knowledge.map(k => <div key={k.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-4"><div><p className="font-medium">{k.name}</p><p className="text-muted-foreground text-xs">{k.shared ? 'Condivisa con tutti' : 'Accesso su assegnazione'} · {k.documents.reduce((n, d) => n + (d.count || 0), 0)} documenti</p></div><Button variant="outline" onClick={() => setEditor({ kind: 'knowledge', id: k.id })}>Gestisci accessi</Button></div>)}{!knowledge.length && <p>Nessuna knowledge base. Creala dalla sezione Knowledge base.</p>}</TabsContent>
      <TabsContent value="models" className="space-y-3"><Button onClick={() => setEditor({ kind: 'model' })}>Aggiungi modello</Button>{models.map(m => <div key={m.key} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-4"><div><p className="font-medium">{m.name}</p><p className="text-muted-foreground text-xs">{m.key} · {m.enabled ? 'Abilitato' : 'Disabilitato'} · {m.shared ? 'Tutti' : 'Assegnato'}</p></div><Button variant="outline" onClick={() => setEditor({ kind: 'model', id: m.key })}>Configura</Button></div>)}</TabsContent>
      <TabsContent value="usage"><UsagePanel users={users} /></TabsContent>
      <TabsContent value="audit" className="space-y-3">{audit.map(entry => <div key={entry.id} className="border-b py-3 text-sm"><p>{entry.action} · {users.find(u => u.id === entry.actor_id)?.email || entry.actor_id}</p><p className="text-muted-foreground text-xs">{new Date(entry.created_at).toLocaleString('it-IT')} · {entry.target}</p></div>)}<div className="flex gap-3"><Button variant="outline" disabled={!auditOffset} onClick={() => setAuditOffset(v => Math.max(0, v - 100))}>Precedenti</Button><Button variant="outline" disabled={audit.length < 100} onClick={() => setAuditOffset(v => v + 100)}>Successivi</Button></div></TabsContent>
    </Tabs>
    <Dialog open={!!editor} onOpenChange={open => !open && setEditor(null)}><DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-xl"><DialogHeader><DialogTitle>{editor?.kind === 'user' ? 'Gestisci utente' : editor?.kind === 'create-user' ? 'Nuovo utente' : editor?.kind === 'knowledge' ? 'Accessi knowledge base' : 'Configura modello'}</DialogTitle><DialogDescription>Le modifiche ai permessi vengono verificate anche dal server e registrate.</DialogDescription></DialogHeader>
      {editor?.kind === 'user' && users.find(u => u.id === editor.id) && <UserEditor key={editor.id} user={users.find(u => u.id === editor.id)!} onSaved={saved} />}
      {editor?.kind === 'create-user' && <CreateUserForm onSaved={saved} />}
      {editor?.kind === 'knowledge' && knowledge.find(k => k.id === editor.id) && <KnowledgeEditor key={editor.id} kb={knowledge.find(k => k.id === editor.id)!} users={users} initial={kbMembers.filter(m => m.knowledge_id === editor.id)} onSaved={saved} />}
      {editor?.kind === 'model' && <ModelEditor key={editor.id || 'new'} model={models.find(m => m.key === editor.id)} users={users} initial={modelMembers.filter(m => m.model_key === editor.id)} onSaved={saved} />}
    </DialogContent></Dialog>
  </div></div>;
}
