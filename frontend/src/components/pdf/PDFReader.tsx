import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import { ChevronLeft, ChevronRight, Crosshair, LoaderCircle, Minus, Plus, X } from 'lucide-react';
import { authFetch } from '@/auth/supabase';
import { Button } from '@/components/ui/button';
import { matchingRanges, normalized, renderHighlighted } from './highlight';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';

pdfjs.GlobalWorkerOptions.workerSrc = new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url).toString();
export interface PDFSelection {
  knowledgeId: string; documentId: string; pageStart: number; pageEnd?: number;
  text?: string; filename?: string; score?: number;
}
function HighlightPage({ page, width, text, onRendered }: { page: number; width: number; text: string; onRendered: () => void }) {
  const [items, setItems] = useState<{ str: string; index: number }[]>([]);
  const ranges = useMemo(() => matchingRanges(items.map(i => i.str).join(''), text), [items, text]);
  const offsets = useMemo(() => {
    let offset = 0; const result = new Map<number, number>();
    for (const item of items) { result.set(item.index, offset); offset += normalized(item.str).length; }
    return result;
  }, [items]);
  return <Page pageNumber={page} width={width} onRenderTextLayerSuccess={onRendered}
    onGetTextSuccess={content => setItems(content.items.flatMap((item, index) => 'str' in item ? [{ str: item.str, index }] : []))}
    customTextRenderer={({ str, itemIndex }) => renderHighlighted(str, offsets.get(itemIndex) ?? 0, ranges)} />;
}
export default function PDFReader({ selection, onClose }: { selection: PDFSelection; onClose: () => void }) {
  const { knowledgeId, documentId, filename, pageStart, pageEnd, text = '' } = selection;
  const [data, setData] = useState<Uint8Array | null>(null);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(Math.max(1, pageStart));
  const [zoom, setZoom] = useState(1);
  const [width, setWidth] = useState(600);
  const [contextOpen, setContextOpen] = useState(false);
  const container = useRef<HTMLDivElement>(null);
  const jump = useRef(true);
  useEffect(() => {
    const controller = new AbortController();
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset state when the external document request changes
    setData(null); setError(''); setCount(0);
    authFetch(`${import.meta.env.VITE_API_URL || ''}/api/knowledge/${knowledgeId}/documents/${documentId}/file`, { signal: controller.signal })
      .then(res => { if (!res.ok) throw new Error('Documento non disponibile o accesso negato.'); return res.arrayBuffer(); })
      .then(buffer => { if (!controller.signal.aborted) setData(new Uint8Array(buffer)); })
      .catch(err => { if (!controller.signal.aborted) setError(err.message || 'Caricamento non riuscito.'); });
    return () => controller.abort();
  }, [knowledgeId, documentId, retry]);
  // eslint-disable-next-line react-hooks/set-state-in-effect -- follow a newly selected external citation
  useEffect(() => { setPage(Math.max(1, pageStart)); jump.current = true; }, [pageStart, text, documentId]);
  useEffect(() => {
    if (!container.current) return;
    const observer = new ResizeObserver(entries => setWidth(Math.max(180, entries[0].contentRect.width - 40)));
    observer.observe(container.current); return () => observer.disconnect();
  }, []);
  const file = useMemo(() => data ? { data } : null, [data]);
  const rendered = useCallback(() => {
    if (!jump.current) return;
    const highlight = container.current?.querySelector('.pdf-highlight');
    if (highlight) { highlight.scrollIntoView({ block: 'center', inline: 'nearest' }); jump.current = false; }
  }, []);
  return <section className="bg-muted flex h-full min-h-0 min-w-0 flex-col" aria-label="Documento fonte">
    <div className="bg-background flex shrink-0 flex-wrap items-center gap-1 border-b p-2">
      <span className="mr-auto max-w-64 truncate px-2 text-sm font-medium" title={filename}>{filename || 'Documento PDF'}</span>
      <Button variant="ghost" size="icon" aria-label="Pagina precedente" disabled={page <= 1} onClick={() => setPage(p => p - 1)}><ChevronLeft /></Button>
      <span className="text-xs">{page} / {count || '…'}</span>
      <Button variant="ghost" size="icon" aria-label="Pagina successiva" disabled={!count || page >= count} onClick={() => setPage(p => p + 1)}><ChevronRight /></Button>
      <Button variant="ghost" size="icon" aria-label="Riduci zoom" onClick={() => setZoom(z => Math.max(.5, z - .2))}><Minus /></Button>
      <Button variant="ghost" size="icon" aria-label="Aumenta zoom" onClick={() => setZoom(z => Math.min(3, z + .2))}><Plus /></Button>
      <Button variant="ghost" size="icon" aria-label="Vai alla fonte" onClick={() => { setPage(Math.min(count || pageStart, Math.max(1, pageStart))); jump.current = true; if (page === Math.min(count || pageStart, Math.max(1, pageStart))) rendered(); }}><Crosshair /></Button>
      <Button variant="ghost" size="icon" aria-label="Chiudi documento" onClick={onClose}><X /></Button>
    </div>
    {text && <div className="bg-background shrink-0 border-b px-3 py-2 text-xs">
      <button className="text-primary" onClick={() => setContextOpen(v => !v)} aria-expanded={contextOpen}>Passaggio fonte · p. {pageStart}{pageEnd && pageEnd !== pageStart ? `–${pageEnd}` : ''} · {contextOpen ? 'Nascondi testo' : 'Mostra testo'}</button>
      {contextOpen && <p className="mt-2 max-h-32 overflow-auto whitespace-pre-wrap leading-relaxed">{text}</p>}
    </div>}
    <div ref={container} className="min-h-0 flex-1 overflow-auto p-4">
      {error ? <div role="alert" className="space-y-3 p-6 text-center"><p>{error}</p><Button onClick={() => setRetry(v => v + 1)}>Riprova</Button></div> : !file ? <div role="status" className="flex justify-center gap-2 p-8"><LoaderCircle className="animate-spin" />Caricamento PDF…</div> :
        <Document file={file} onLoadSuccess={({ numPages }) => { setCount(numPages); setPage(p => Math.min(numPages, Math.max(1, p))); }} onLoadError={() => setError('PDF non leggibile.')} loading="Apertura documento…">
          <HighlightPage key={`${documentId}:${page}`} page={page} width={width * zoom} text={page >= pageStart && page <= (pageEnd ?? pageStart) ? text : ''} onRendered={rendered} />
        </Document>}
    </div>
    <style>{`.pdf-highlight{background:rgba(251,191,36,.5)!important;color:transparent}.react-pdf__Page{margin:auto}.react-pdf__Page__textContent mark{color:transparent}`}</style>
  </section>;
}
