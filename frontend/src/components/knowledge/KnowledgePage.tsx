import { useReader } from '@/context/ReaderContext';
import { useProfile } from '@/auth/AuthContext';
import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { Clock3, FileText, FolderPlus, Loader2, Plus, RotateCcw, Settings2, Trash2, Upload, Users } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
  createKnowledge,
  deleteDocument,
  deleteKnowledge,
  fetchDocuments,
  retryImport,
  uploadDocuments,
  updateKnowledge,
  type DocumentItem,
  type ImportJobItem,
  type KnowledgeItem,
  type KnowledgeVisibility,
} from '@/api/client';
import { KnowledgeAccessForm } from '@/components/knowledge/KnowledgeAccessForm';
import { permissionLabel, selectClass, visibilityLabel } from '@/lib/knowledge';
import { useApp } from '@/context/AppContext';
import { cn } from '@/lib/utils';
import { errorMessage, formatDate } from '@/lib/format';
import { PageHeader } from '@/components/layout/AppLayout';

type Pending =
  | { kind: 'kb'; item: KnowledgeItem }
  | { kind: 'doc'; item: DocumentItem }
  | null;

export function KnowledgePage() {
  const reader = useReader();
  const { canCreateKnowledge } = useProfile();
  const { knowledges, reloadKnowledges, selectedKnowledgeId, setSelectedKnowledgeId } = useApp();
  const selected = knowledges.find((k) => k.id === selectedKnowledgeId) ?? null;
  // Permessi calcolati dal database e restituiti dall'API.
  const canEdit = !!selected?.can_edit;
  const canOwn = !!selected?.can_own;
  const [dialog, setDialog] = useState<'share' | 'edit' | null>(null);

  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [jobs, setJobs] = useState<ImportJobItem[]>([]);
  const [docsLoading, setDocsLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [pending, setPending] = useState<Pending>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const loadDocuments = useCallback(async (kbId: string, silent = false) => {
    if (!silent) setDocsLoading(true);
    try {
      const data = await fetchDocuments(kbId);
      setDocuments(data.documents);
      setJobs(data.jobs);
    } catch (err) {
      if (!silent) {
        toast.error(errorMessage(err, 'Errore caricamento documenti'));
        setDocuments([]);
        setJobs([]);
      }
    } finally {
      if (!silent) setDocsLoading(false);
    }
  }, []);

  const selectedId = selected?.id;
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch al cambio di selezione
    if (selectedId) loadDocuments(selectedId);
  }, [selectedId, loadDocuments]);

  const hasRunningJobs = jobs.some((job) => job.status === 'queued' || job.status === 'running');
  useEffect(() => {
    if (!selectedId || !hasRunningJobs) return;
    const timer = window.setInterval(async () => {
      await Promise.all([loadDocuments(selectedId, true), reloadKnowledges()]);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [selectedId, hasRunningJobs, loadDocuments, reloadKnowledges]);

  const upload = async (files: File[]) => {
    if (!selected || !canEdit) return;
    const pdfs = files.filter((f) => f.type === 'application/pdf' || f.name.toLowerCase().endsWith('.pdf'));
    if (pdfs.length === 0) {
      toast.error('Solo file PDF');
      return;
    }
    setUploading(true);
    const id = toast.loading(`Caricamento di ${pdfs.length} file…`);
    try {
      const res = await uploadDocuments(selected.id, pdfs);
      if (res.total_errors > 0) {
        toast.warning(`${res.total_queued} messi in coda, ${res.total_errors} con errori`, {
          id,
          description: res.errors.map((e) => `${e.filename}: ${e.error}`).join('\n'),
        });
      } else {
        toast.success(`${res.total_queued} file messi in coda`, { id });
      }
      await Promise.all([loadDocuments(selected.id), reloadKnowledges()]);
    } catch (err) {
      toast.error(errorMessage(err, 'Caricamento non riuscito'), { id });
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = '';
    }
  };

  const retry = async (job: ImportJobItem) => {
    if (!selected) return;
    try {
      await retryImport(selected.id, job.id);
      toast.success(`Nuovo tentativo avviato per «${job.filename}»`);
      await loadDocuments(selected.id, true);
    } catch (err) {
      toast.error(errorMessage(err, 'Impossibile riprovare l’importazione'));
    }
  };

  const confirmDelete = async () => {
    if (!pending) return;
    try {
      if (pending.kind === 'kb') {
        await deleteKnowledge(pending.item.id);
        await reloadKnowledges();
        toast.success('Knowledge base eliminata');
      } else if (selected) {
        await deleteDocument(selected.id, pending.item.document_id);
        await Promise.all([loadDocuments(selected.id), reloadKnowledges()]);
        toast.success('Documento eliminato');
      }
    } catch (err) {
      toast.error(errorMessage(err, 'Eliminazione non riuscita'));
    } finally {
      setPending(null);
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <PageHeader title="Knowledge base">
        {canCreateKnowledge && <CreateKnowledgeDialog
          onCreated={async (kb) => {
            await reloadKnowledges();
            setSelectedKnowledgeId(kb.id);
          }}
        />}
      </PageHeader>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto grid max-w-6xl gap-6 p-4 md:grid-cols-[280px_1fr] md:p-6">
          <section aria-label="Elenco knowledge base" className="space-y-2">
            {knowledges.length === 0 && (
              <p className="text-muted-foreground text-sm">
                {canCreateKnowledge ? 'Nessuna knowledge base: creane una con «Nuova».' : 'Nessuna knowledge base condivisa con te.'}
              </p>
            )}
            {knowledges.map((kb) => (
              <Card
                key={kb.id}
                role="button"
                tabIndex={0}
                onClick={() => setSelectedKnowledgeId(kb.id)}
                onKeyDown={(e) => e.key === 'Enter' && setSelectedKnowledgeId(kb.id)}
                className={cn(
                  'hover:bg-accent/50 cursor-pointer gap-0 py-3 transition-colors',
                  kb.id === selectedKnowledgeId && 'border-primary ring-primary/20 ring-2',
                )}
              >
                <CardHeader className="px-4">
                  <CardTitle className="flex items-center justify-between gap-2 text-sm">
                    <span className="truncate">{kb.name}</span>
                    <Badge variant="secondary">{kb.documents_count}</Badge>
                  </CardTitle>
                  <p className="text-muted-foreground text-xs">
                    {kb.permission ? permissionLabel[kb.permission] : ''} · {visibilityLabel[kb.visibility]}
                  </p>
                  {kb.description && (
                    <CardDescription className="line-clamp-2 text-xs">{kb.description}</CardDescription>
                  )}
                </CardHeader>
              </Card>
            ))}
          </section>

          <section aria-label="Documenti" className="min-w-0 space-y-4">
            {!selected ? (
              <div className="text-muted-foreground flex h-64 items-center justify-center rounded-xl border border-dashed text-sm">
                Seleziona una knowledge base
              </div>
            ) : (
              <>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <h2 className="truncate text-lg font-semibold">{selected.name}</h2>
                    <p className="text-muted-foreground text-sm">
                      Creata il {formatDate(selected.created_at)} · {selected.documents_count} documenti · {visibilityLabel[selected.visibility]}
                    </p>
                    {selected.description && <p className="text-muted-foreground mt-1 text-sm">{selected.description}</p>}
                  </div>
                  {canOwn && <div className="flex gap-1">
                    <Button variant="ghost" size="sm" onClick={() => setDialog('edit')}><Settings2 /> Modifica</Button>
                    <Button variant="ghost" size="sm" onClick={() => setDialog('share')}><Users /> Condividi</Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-destructive hover:text-destructive"
                      onClick={() => setPending({ kind: 'kb', item: selected })}
                    >
                      <Trash2 /> Elimina
                    </Button>
                  </div>}
                </div>
                {!canEdit && (
                  <p className="text-muted-foreground rounded-lg border px-3 py-2 text-sm">
                    Accesso in sola lettura: puoi consultare i documenti e usarli in chat.
                  </p>
                )}

                {canEdit && <button
                  type="button"
                  disabled={uploading}
                  onClick={() => fileInput.current?.click()}
                  onDragOver={(e) => {
                    e.preventDefault();
                    setDragOver(true);
                  }}
                  onDragLeave={() => setDragOver(false)}
                  onDrop={(e) => {
                    e.preventDefault();
                    setDragOver(false);
                    upload(Array.from(e.dataTransfer.files));
                  }}
                  className={cn(
                    'hover:bg-accent/40 flex w-full flex-col items-center gap-2 rounded-xl border-2 border-dashed px-4 py-8 text-center transition-colors disabled:opacity-60',
                    dragOver && 'border-primary bg-accent/40',
                  )}
                >
                  {uploading ? (
                    <Loader2 className="text-muted-foreground size-6 animate-spin" />
                  ) : (
                    <Upload className="text-muted-foreground size-6" />
                  )}
                  <span className="text-sm font-medium">
                    {uploading ? 'Caricamento in corso…' : 'Trascina qui i PDF o clicca per sceglierli'}
                  </span>
                  <span className="text-muted-foreground text-xs">
                    I PDF vengono messi in coda e indicizzati in modo recuperabile
                  </span>
                </button>}
                <input
                  ref={fileInput}
                  type="file"
                  accept="application/pdf,.pdf"
                  multiple
                  hidden
                  onChange={(e) => upload(Array.from(e.target.files ?? []))}
                />

                {jobs.length > 0 && <div className="divide-y rounded-xl border" aria-label="Importazioni">
                  {jobs.map((job) => (
                    <div key={job.id} className="flex items-center gap-3 p-3">
                      <div className="bg-muted flex size-8 shrink-0 items-center justify-center rounded-md">
                        {job.status === 'running'
                          ? <Loader2 className="text-primary size-4 animate-spin" />
                          : <Clock3 className="text-muted-foreground size-4" />}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <p className="truncate text-sm font-medium">{job.filename}</p>
                          <Badge variant={job.status === 'failed' ? 'destructive' : 'secondary'}>
                            {job.status === 'queued' ? 'In coda' : job.status === 'failed' ? 'Errore' : importStageLabel(job.stage)}
                          </Badge>
                        </div>
                        {job.status === 'failed' ? (
                          <p className="text-destructive mt-1 text-xs">{job.last_error_message || 'Importazione non riuscita'}</p>
                        ) : (
                          <div className="bg-muted mt-2 h-1.5 overflow-hidden rounded-full">
                            <div className="bg-primary h-full transition-all" style={{ width: `${job.progress}%` }} />
                          </div>
                        )}
                        <p className="text-muted-foreground mt-1 text-xs">
                          Tentativo {job.attempts}/{job.max_attempts} · {job.progress}%
                        </p>
                      </div>
                      {canEdit && job.status === 'failed' && <Button
                        variant="outline" size="sm" onClick={() => retry(job)}
                      >
                        <RotateCcw /> Riprova
                      </Button>}
                    </div>
                  ))}
                </div>}

                <div className="divide-y rounded-xl border">
                  {docsLoading ? (
                    Array.from({ length: 3 }).map((_, i) => (
                      <div key={i} className="flex items-center gap-3 p-3">
                        <Skeleton className="size-8 rounded-md" />
                        <Skeleton className="h-4 flex-1" />
                      </div>
                    ))
                  ) : documents.length === 0 ? (
                    <p className="text-muted-foreground p-6 text-center text-sm">Nessun documento caricato</p>
                  ) : (
                    documents.map((doc) => (
                      <div key={doc.document_id} className="group flex items-center gap-3 p-3">
                        <div className="bg-muted flex size-8 shrink-0 items-center justify-center rounded-md">
                          <FileText className="text-muted-foreground size-4" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <button
                            onClick={() => reader.open({ knowledgeId: selected.id, documentId: doc.document_id, pageStart: 1, filename: doc.filename })}
                            className="block truncate text-sm font-medium hover:underline"
                          >
                            {doc.filename}
                          </button>
                          <p className="text-muted-foreground text-xs">
                            {formatDate(doc.uploaded_at)} · {doc.chunks_count} parti
                          </p>
                        </div>
                        {canEdit && <Button
                          variant="ghost"
                          size="icon"
                          className="size-8 opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
                          aria-label={`Elimina ${doc.filename}`}
                          onClick={() => setPending({ kind: 'doc', item: doc })}
                        >
                          <Trash2 className="size-4" />
                        </Button>}
                      </div>
                    ))
                  )}
                </div>
              </>
            )}
          </section>
        </div>
      </div>

      <Dialog open={!!selected && dialog !== null} onOpenChange={(open) => !open && setDialog(null)}>
        <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>{dialog === 'share' ? 'Condividi knowledge base' : 'Modifica knowledge base'}</DialogTitle>
            <DialogDescription>{selected?.name}</DialogDescription>
          </DialogHeader>
          {selected && dialog === 'share' && (
            <KnowledgeAccessForm knowledgeId={selected.id} onSaved={() => { setDialog(null); reloadKnowledges(); }} />
          )}
          {selected && dialog === 'edit' && (
            <EditKnowledgeForm kb={selected} onSaved={async () => { setDialog(null); await reloadKnowledges(); }} />
          )}
        </DialogContent>
      </Dialog>

      <AlertDialog open={pending !== null} onOpenChange={(open) => !open && setPending(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {pending?.kind === 'kb' ? 'Eliminare la knowledge base?' : 'Eliminare il documento?'}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {pending?.kind === 'kb'
                ? `«${pending.item.name}», tutti i suoi documenti e l'indice verranno cancellati.`
                : pending
                  ? `«${pending.item.filename}» verrà rimosso dall'indice e dal disco.`
                  : ''}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Annulla</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={confirmDelete}>
              Elimina
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function importStageLabel(stage: ImportJobItem['stage']) {
  return ({
    queued: 'In coda', extracting: 'Estrazione', embedding: 'Embedding',
    indexing: 'Indicizzazione', publishing: 'Pubblicazione', failed: 'Errore',
  })[stage];
}

function CreateKnowledgeDialog({ onCreated }: { onCreated: (kb: KnowledgeItem) => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [visibility, setVisibility] = useState<KnowledgeVisibility>('private');
  const [saving, setSaving] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    try {
      const kb = await createKnowledge(name.trim(), description.trim(), visibility);
      await onCreated(kb);
      toast.success(`Creata «${kb.name}»`);
      setOpen(false);
      setName('');
      setDescription('');
    } catch (err) {
      toast.error(errorMessage(err, 'Creazione non riuscita'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <Plus /> Nuova
        </Button>
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={submit} className="space-y-4">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FolderPlus className="size-5" /> Nuova knowledge base
            </DialogTitle>
            <DialogDescription>Un insieme di documenti su cui il chatbot risponde.</DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="kb-name">Nome</Label>
            <Input id="kb-name" value={name} onChange={(e) => setName(e.target.value)} autoFocus required />
          </div>
          <div className="space-y-2">
            <Label htmlFor="kb-desc">Descrizione</Label>
            <Textarea
              id="kb-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Facoltativa"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="kb-new-visibility">Visibilità</Label>
            <select id="kb-new-visibility" className={`${selectClass} w-full`} value={visibility} onChange={(e) => setVisibility(e.target.value as KnowledgeVisibility)}>
              <option value="private">{visibilityLabel.private}: solo tu e chi inviterai</option>
              <option value="organization">{visibilityLabel.organization}: tutti possono leggerla</option>
            </select>
            <p className="text-muted-foreground text-xs">Ne sarai il proprietario. Gli amministratori possono sempre accedervi.</p>
          </div>
          <DialogFooter>
            <Button type="submit" disabled={saving || !name.trim()}>
              {saving && <Loader2 className="animate-spin" />} Crea
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function EditKnowledgeForm({ kb, onSaved }: { kb: KnowledgeItem; onSaved: () => Promise<void> }) {
  const [name, setName] = useState(kb.name);
  const [description, setDescription] = useState(kb.description);
  const [saving, setSaving] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    try {
      await updateKnowledge(kb.id, name.trim(), description.trim());
      toast.success('Knowledge base aggiornata');
      await onSaved();
    } catch (err) {
      toast.error(errorMessage(err, 'Salvataggio non riuscito'));
    } finally {
      setSaving(false);
    }
  };
  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="kb-edit-name">Nome</Label>
        <Input id="kb-edit-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={200} required />
      </div>
      <div className="space-y-2">
        <Label htmlFor="kb-edit-desc">Descrizione</Label>
        <Textarea id="kb-edit-desc" value={description} onChange={(e) => setDescription(e.target.value)} maxLength={2000} />
      </div>
      <DialogFooter>
        <Button type="submit" disabled={saving || !name.trim()}>{saving && <Loader2 className="animate-spin" />} Salva</Button>
      </DialogFooter>
    </form>
  );
}
