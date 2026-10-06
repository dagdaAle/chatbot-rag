import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { FileText, FolderPlus, Loader2, Plus, Trash2, Upload } from 'lucide-react';
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
  getDocumentFileUrl,
  uploadDocuments,
  type DocumentItem,
  type KnowledgeItem,
} from '@/api/client';
import { useApp } from '@/context/AppContext';
import { cn } from '@/lib/utils';
import { errorMessage, formatDate } from '@/lib/format';
import { PageHeader } from '@/components/layout/AppLayout';

type Pending =
  | { kind: 'kb'; item: KnowledgeItem }
  | { kind: 'doc'; item: DocumentItem }
  | null;

export function KnowledgePage() {
  const { knowledges, reloadKnowledges, selectedKnowledgeId, setSelectedKnowledgeId } = useApp();
  const selected = knowledges.find((k) => k.id === selectedKnowledgeId) ?? null;

  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [docsLoading, setDocsLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [pending, setPending] = useState<Pending>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const loadDocuments = useCallback(async (kbId: string) => {
    setDocsLoading(true);
    try {
      const data = await fetchDocuments(kbId);
      setDocuments(data.documents);
    } catch (err) {
      toast.error(errorMessage(err, 'Errore caricamento documenti'));
      setDocuments([]);
    } finally {
      setDocsLoading(false);
    }
  }, []);

  const selectedId = selected?.id;
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch al cambio di selezione
    if (selectedId) loadDocuments(selectedId);
  }, [selectedId, loadDocuments]);

  const upload = async (files: File[]) => {
    if (!selected) return;
    const pdfs = files.filter((f) => f.type === 'application/pdf' || f.name.toLowerCase().endsWith('.pdf'));
    if (pdfs.length === 0) {
      toast.error('Solo file PDF');
      return;
    }
    setUploading(true);
    const id = toast.loading(`Indicizzazione di ${pdfs.length} file…`);
    try {
      const res = await uploadDocuments(selected.id, pdfs);
      if (res.total_errors > 0) {
        toast.warning(`${res.total_uploaded} caricati, ${res.total_errors} con errori`, {
          id,
          description: res.errors.map((e) => `${e.filename}: ${e.error}`).join('\n'),
        });
      } else {
        toast.success(`${res.total_uploaded} file indicizzati`, { id });
      }
      await Promise.all([loadDocuments(selected.id), reloadKnowledges()]);
    } catch (err) {
      toast.error(errorMessage(err, 'Caricamento non riuscito'), { id });
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = '';
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
        <CreateKnowledgeDialog
          onCreated={async (kb) => {
            await reloadKnowledges();
            setSelectedKnowledgeId(kb.id);
          }}
        />
      </PageHeader>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto grid max-w-6xl gap-6 p-4 md:grid-cols-[280px_1fr] md:p-6">
          <section aria-label="Elenco knowledge base" className="space-y-2">
            {knowledges.length === 0 && (
              <p className="text-muted-foreground text-sm">Nessuna knowledge base. Creane una per iniziare.</p>
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
                Seleziona o crea una knowledge base
              </div>
            ) : (
              <>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <h2 className="truncate text-lg font-semibold">{selected.name}</h2>
                    <p className="text-muted-foreground text-sm">
                      Creata il {formatDate(selected.created_at)} · {selected.documents_count} documenti
                    </p>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-destructive hover:text-destructive"
                    onClick={() => setPending({ kind: 'kb', item: selected })}
                  >
                    <Trash2 /> Elimina
                  </Button>
                </div>

                <button
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
                    {uploading ? 'Indicizzazione in corso…' : 'Trascina qui i PDF o clicca per sceglierli'}
                  </span>
                  <span className="text-muted-foreground text-xs">
                    Il testo viene estratto, diviso in parti e indicizzato
                  </span>
                </button>
                <input
                  ref={fileInput}
                  type="file"
                  accept="application/pdf,.pdf"
                  multiple
                  hidden
                  onChange={(e) => upload(Array.from(e.target.files ?? []))}
                />

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
                          <a
                            href={getDocumentFileUrl(selected.id, doc.document_id)}
                            target="_blank"
                            rel="noreferrer"
                            className="block truncate text-sm font-medium hover:underline"
                          >
                            {doc.filename}
                          </a>
                          <p className="text-muted-foreground text-xs">
                            {formatDate(doc.uploaded_at)} · {doc.chunks_count} parti
                          </p>
                        </div>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="size-8 opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
                          aria-label={`Elimina ${doc.filename}`}
                          onClick={() => setPending({ kind: 'doc', item: doc })}
                        >
                          <Trash2 className="size-4" />
                        </Button>
                      </div>
                    ))
                  )}
                </div>
              </>
            )}
          </section>
        </div>
      </div>

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

function CreateKnowledgeDialog({ onCreated }: { onCreated: (kb: KnowledgeItem) => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [saving, setSaving] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    try {
      const kb = await createKnowledge(name.trim(), description.trim());
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
