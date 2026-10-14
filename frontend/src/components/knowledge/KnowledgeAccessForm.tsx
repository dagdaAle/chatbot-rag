import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  fetchDirectory,
  fetchKnowledgeAccess,
  saveKnowledgeAccess,
  type DirectoryUser,
  type KnowledgeMember,
  type KnowledgeVisibility,
} from '@/api/client';
import { errorMessage } from '@/lib/format';
import { selectClass, visibilityLabel } from '@/lib/knowledge';

type Level = 'none' | KnowledgeMember['role'];

/**
 * Condivisione di una knowledge: usata dal proprietario (pagina Knowledge) e
 * dall'amministratore (pannello Admin, con trasferimento della proprietà).
 * Il server rivalida tutto: qui si mostrano solo le scelte sensate.
 */
export function KnowledgeAccessForm({ knowledgeId, allowOwnerTransfer = false, onSaved }: {
  knowledgeId: string;
  allowOwnerTransfer?: boolean;
  onSaved: () => void;
}) {
  const [users, setUsers] = useState<DirectoryUser[] | null>(null);
  const [visibility, setVisibility] = useState<KnowledgeVisibility>('private');
  const [owner, setOwner] = useState('');
  const [levels, setLevels] = useState<Record<string, Level>>({});
  const [filter, setFilter] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    Promise.all([fetchKnowledgeAccess(knowledgeId), fetchDirectory()])
      .then(([access, directory]) => {
        if (!alive) return;
        setUsers(directory);
        setVisibility(access.visibility);
        setOwner(access.owner_user_id);
        setLevels(Object.fromEntries(access.members.map((m) => [m.user_id, m.role])));
      })
      .catch((err) => alive && setError(errorMessage(err, 'Impossibile caricare gli accessi')));
    return () => { alive = false; };
  }, [knowledgeId]);

  // Gli amministratori accedono sempre; il proprietario non è un membro.
  const assignable = useMemo(
    () => (users ?? []).filter((u) => u.role !== 'admin' && u.id !== owner
      && `${u.display_name} ${u.email}`.toLowerCase().includes(filter.toLowerCase())),
    [users, owner, filter],
  );
  const owners = (users ?? []).filter((u) => u.role !== 'viewer');

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    const members = Object.entries(levels)
      .filter(([id, level]) => level !== 'none' && id !== owner)
      .map(([user_id, role]) => ({ user_id, role: role as KnowledgeMember['role'] }));
    try {
      await saveKnowledgeAccess(knowledgeId, { visibility, members, ...(allowOwnerTransfer ? { owner_user_id: owner } : {}) });
      toast.success('Accessi aggiornati');
      onSaved();
    } catch (err) {
      setError(errorMessage(err, 'Salvataggio non riuscito'));
    } finally {
      setBusy(false);
    }
  }

  if (!users) {
    return error
      ? <p role="alert" className="text-destructive text-sm">{error}</p>
      : <p role="status" className="text-muted-foreground flex items-center gap-2 text-sm"><Loader2 className="size-4 animate-spin" /> Caricamento accessi…</p>;
  }

  return (
    <form className="space-y-4" onSubmit={submit}>
      <div className="grid gap-2">
        <Label htmlFor="kb-visibility">Visibilità</Label>
        <select id="kb-visibility" className={selectClass} value={visibility} onChange={(e) => setVisibility(e.target.value as KnowledgeVisibility)}>
          <option value="private">{visibilityLabel.private}: solo le persone assegnate</option>
          <option value="organization">{visibilityLabel.organization}: tutti possono leggere</option>
        </select>
        <p className="text-muted-foreground text-xs">Gli amministratori accedono sempre. In ogni caso solo proprietario ed editor modificano i documenti.</p>
      </div>

      {allowOwnerTransfer && (
        <div className="grid gap-2">
          <Label htmlFor="kb-owner">Proprietario</Label>
          <select id="kb-owner" className={selectClass} value={owner} onChange={(e) => setOwner(e.target.value)}>
            {owners.map((u) => <option key={u.id} value={u.id}>{u.display_name || u.email}</option>)}
          </select>
        </div>
      )}

      <div className="grid gap-2">
        <Label htmlFor="kb-members-filter">Persone</Label>
        <Input id="kb-members-filter" placeholder="Cerca nome o email" value={filter} onChange={(e) => setFilter(e.target.value)} />
        <div className="max-h-64 divide-y overflow-auto rounded-md border">
          {assignable.map((u) => (
            <div key={u.id} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
              <div className="min-w-0">
                <p className="truncate">{u.display_name || u.email}</p>
                {u.display_name && <p className="text-muted-foreground truncate text-xs">{u.email}</p>}
              </div>
              <select
                aria-label={`Accesso di ${u.display_name || u.email}`}
                className={selectClass}
                value={levels[u.id] ?? 'none'}
                onChange={(e) => setLevels({ ...levels, [u.id]: e.target.value as Level })}
              >
                <option value="none">{visibility === 'organization' ? 'Lettura (organizzazione)' : 'Nessun accesso'}</option>
                <option value="viewer">Lettore</option>
                <option value="editor" disabled={u.role === 'viewer'}>Editor{u.role === 'viewer' ? ' (account in sola lettura)' : ''}</option>
              </select>
            </div>
          ))}
          {!assignable.length && <p className="text-muted-foreground p-3 text-sm">Nessun utente da assegnare.</p>}
        </div>
      </div>

      {error && <p role="alert" className="text-destructive text-sm">{error}</p>}
      <Button type="submit" disabled={busy}>{busy && <Loader2 className="animate-spin" />} Salva accessi</Button>
    </form>
  );
}
