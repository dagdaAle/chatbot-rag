import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';

// Configura il worker PDF.js
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString();

const API_URL = import.meta.env.VITE_API_URL || '';

/* ─── Helpers ─────────────────────────────────────────── */

/**
 * Estrae sotto-stringhe significative dal testo del chunk
 * per confrontarle con il testo della text-layer PDF.
 */
function buildSearchFragments(text: string, fragLen = 40): string[] {
  if (!text || text.length < 10) return [];
  const cleaned = text.replace(/\s+/g, ' ').trim();
  const fragments: string[] = [];
  // Prendi frammenti distribuiti nel testo
  const step = Math.max(1, Math.floor(cleaned.length / 8));
  for (let i = 0; i < cleaned.length - fragLen; i += step) {
    const frag = cleaned.slice(i, i + fragLen).trim();
    if (frag.length >= 15) {
      fragments.push(frag.toLowerCase());
    }
    if (fragments.length >= 12) break;
  }
  return fragments;
}

/* ─── Component ───────────────────────────────────────── */

const PDFViewerPage: React.FC = () => {
  const [searchParams] = useSearchParams();

  // Parametri dalla URL
  const knowledgeId = searchParams.get('kb') || '';
  const documentId = searchParams.get('doc') || '';
  const targetPage = parseInt(searchParams.get('page') || '1', 10);
  const chunkText = searchParams.get('text') || '';
  const filename = searchParams.get('filename') || 'documento.pdf';
  const score = parseFloat(searchParams.get('score') || '0');
  const pageEnd = parseInt(searchParams.get('pageEnd') || String(targetPage), 10);

  // State
  const [numPages, setNumPages] = useState<number>(0);
  const [scale, setScale] = useState(1.2);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const [loadingPdf, setLoadingPdf] = useState(true);

  // Refs
  const targetPageRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // URL del PDF dal backend
  const pdfUrl = useMemo(
    () => `${API_URL}/api/knowledge/${knowledgeId}/documents/${documentId}/file`,
    [knowledgeId, documentId],
  );

  // Frammenti di testo per l'evidenziazione
  const searchFragments = useMemo(() => buildSearchFragments(chunkText), [chunkText]);

  // Scroll alla pagina target dopo il caricamento
  useEffect(() => {
    if (numPages > 0 && targetPageRef.current) {
      // Piccolo delay per assicurarsi che il render sia completo
      const timer = setTimeout(() => {
        targetPageRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }, 400);
      return () => clearTimeout(timer);
    }
  }, [numPages]);

  const onDocumentLoadSuccess = useCallback(({ numPages: n }: { numPages: number }) => {
    setNumPages(n);
    setLoadingPdf(false);
    setPdfError(null);
  }, []);

  const onDocumentLoadError = useCallback((error: Error) => {
    console.error('PDF load error:', error);
    setPdfError('Impossibile caricare il PDF. Verifica che il documento esista.');
    setLoadingPdf(false);
  }, []);

  // Custom text renderer per evidenziare il testo del chunk
  const customTextRenderer = useCallback(
    (textItem: { str: string; itemIndex: number }) => {
      if (searchFragments.length === 0) return textItem.str;
      const lowerStr = textItem.str.toLowerCase();
      for (const frag of searchFragments) {
        if (lowerStr.includes(frag) || frag.includes(lowerStr)) {
          return `<mark class="pdf-highlight">${textItem.str}</mark>`;
        }
      }
      return textItem.str;
    },
    [searchFragments],
  );

  // Zoom controls
  const zoomIn = () => setScale((s) => Math.min(s + 0.2, 3));
  const zoomOut = () => setScale((s) => Math.max(s - 0.2, 0.4));
  const zoomReset = () => setScale(1.2);

  // Scroll alla pagina target
  const scrollToTarget = () => {
    targetPageRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  };

  const pageLabel =
    targetPage === pageEnd
      ? `Pagina ${targetPage}`
      : `Pagine ${targetPage}-${pageEnd}`;

  return (
    <div className="flex h-screen w-screen bg-gray-100 overflow-hidden">
      {/* ─── Toolbar ─── */}
      <div className="fixed top-0 left-0 right-0 z-50 h-14 bg-white border-b border-gray-200 shadow-sm flex items-center justify-between px-4">
        {/* Left: back + filename */}
        <div className="flex items-center gap-3 min-w-0">
          <button
            onClick={() => window.close()}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg hover:bg-gray-100 text-gray-600 transition-colors text-sm font-medium shrink-0"
            title="Chiudi"
          >
            <span className="material-symbols-outlined text-[20px]">close</span>
            <span className="hidden sm:inline">Chiudi</span>
          </button>
          <div className="h-6 w-px bg-gray-200 shrink-0" />
          <div className="flex items-center gap-2 min-w-0">
            <span className="material-symbols-outlined text-red-500 text-[20px] shrink-0">picture_as_pdf</span>
            <span className="text-sm font-semibold text-gray-800 truncate">{filename}</span>
          </div>
        </div>

        {/* Center: page info + nav */}
        <div className="flex items-center gap-2">
          <button
            onClick={scrollToTarget}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-50 border border-amber-200 text-amber-700 text-xs font-semibold hover:bg-amber-100 transition-colors"
            title="Vai al passaggio evidenziato"
          >
            <span className="material-symbols-outlined text-[16px]">my_location</span>
            {pageLabel}
          </button>
          {numPages > 0 && (
            <span className="text-xs text-gray-500">di {numPages}</span>
          )}
        </div>

        {/* Right: zoom + sidebar toggle */}
        <div className="flex items-center gap-1.5">
          <button onClick={zoomOut} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-600 transition-colors" title="Zoom out">
            <span className="material-symbols-outlined text-[20px]">remove</span>
          </button>
          <button onClick={zoomReset} className="px-2 py-1 rounded-lg hover:bg-gray-100 text-gray-600 text-xs font-medium transition-colors" title="Reset zoom">
            {Math.round(scale * 100)}%
          </button>
          <button onClick={zoomIn} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-600 transition-colors" title="Zoom in">
            <span className="material-symbols-outlined text-[20px]">add</span>
          </button>
          <div className="h-6 w-px bg-gray-200 mx-1" />
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className={`p-1.5 rounded-lg transition-colors ${sidebarOpen ? 'bg-blue-50 text-blue-600' : 'hover:bg-gray-100 text-gray-600'}`}
            title={sidebarOpen ? 'Chiudi pannello fonte' : 'Apri pannello fonte'}
          >
            <span className="material-symbols-outlined text-[20px]">
              {sidebarOpen ? 'right_panel_open' : 'right_panel_close'}
            </span>
          </button>
        </div>
      </div>

      {/* ─── Main area ─── */}
      <div className="flex flex-1 pt-14 h-full">
        {/* PDF viewer area */}
        <div
          ref={containerRef}
          className={`flex-1 overflow-auto bg-gray-200 transition-all duration-300 ${sidebarOpen ? 'mr-0' : ''}`}
        >
          {/* Loading */}
          {loadingPdf && !pdfError && (
            <div className="flex flex-col items-center justify-center h-full gap-3">
              <div className="w-10 h-10 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
              <p className="text-sm text-gray-500">Caricamento PDF...</p>
            </div>
          )}

          {/* Error */}
          {pdfError && (
            <div className="flex flex-col items-center justify-center h-full gap-3">
              <span className="material-symbols-outlined text-red-400 text-[48px]">error</span>
              <p className="text-sm text-red-600 max-w-md text-center">{pdfError}</p>
            </div>
          )}

          {/* PDF Document */}
          {!pdfError && (
            <Document
              file={pdfUrl}
              onLoadSuccess={onDocumentLoadSuccess}
              onLoadError={onDocumentLoadError}
              loading={null}
              className="flex flex-col items-center gap-4 py-6 px-4"
            >
              {Array.from(new Array(numPages), (_, index) => {
                const pageNumber = index + 1;
                const isTargetPage = pageNumber >= targetPage && pageNumber <= pageEnd;
                return (
                  <div
                    key={`page_${pageNumber}`}
                    ref={pageNumber === targetPage ? targetPageRef : undefined}
                    className={`relative shadow-lg rounded-sm ${isTargetPage ? 'ring-4 ring-amber-400 ring-offset-2' : ''}`}
                  >
                    {/* Page number badge */}
                    <div className="absolute -top-3 left-4 z-10">
                      <span
                        className={`text-[10px] font-bold px-2 py-0.5 rounded-full shadow-sm ${
                          isTargetPage
                            ? 'bg-amber-400 text-amber-900'
                            : 'bg-white text-gray-500 border border-gray-200'
                        }`}
                      >
                        {pageNumber}
                      </span>
                    </div>
                    <Page
                      pageNumber={pageNumber}
                      scale={scale}
                      renderTextLayer={true}
                      renderAnnotationLayer={true}
                      customTextRenderer={isTargetPage ? customTextRenderer : undefined}
                    />
                  </div>
                );
              })}
            </Document>
          )}
        </div>

        {/* ─── Sidebar: chunk context ─── */}
        <aside
          className={`bg-white border-l border-gray-200 shadow-lg flex flex-col transition-all duration-300 overflow-hidden ${
            sidebarOpen ? 'w-80 lg:w-96' : 'w-0'
          }`}
        >
          {sidebarOpen && (
            <>
              {/* Sidebar header */}
              <div className="px-4 py-3 border-b border-gray-100 bg-gray-50/50 shrink-0">
                <div className="flex items-center gap-2 mb-2">
                  <span className="material-symbols-outlined text-amber-600 text-[18px]">auto_awesome</span>
                  <h3 className="text-sm font-bold text-gray-800">Passaggio fonte</h3>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  <span className="text-xs bg-amber-50 text-amber-700 border border-amber-200 px-2 py-0.5 rounded-full font-medium">
                    {pageLabel}
                  </span>
                  {score > 0 && (
                    <span className="text-xs bg-blue-50 text-blue-700 border border-blue-200 px-2 py-0.5 rounded-full font-medium">
                      Rilevanza: {(score * 100).toFixed(0)}%
                    </span>
                  )}
                </div>
              </div>

              {/* Sidebar body: chunk text */}
              <div className="flex-1 overflow-y-auto p-4">
                <div className="mb-3">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="material-symbols-outlined text-gray-400 text-[16px]">description</span>
                    <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Testo estratto</span>
                  </div>
                  <div className="bg-amber-50/50 border border-amber-100 rounded-lg p-3">
                    <p className="text-sm text-gray-800 leading-relaxed whitespace-pre-wrap">
                      {chunkText || 'Nessun testo disponibile.'}
                    </p>
                  </div>
                </div>

                {/* Info aggiuntive */}
                <div className="space-y-2 mt-4">
                  <div className="flex items-center gap-2 text-xs text-gray-500">
                    <span className="material-symbols-outlined text-[14px]">folder</span>
                    <span className="truncate">{filename}</span>
                  </div>
                  {score > 0 && (
                    <div className="flex items-center gap-2 text-xs text-gray-500">
                      <span className="material-symbols-outlined text-[14px]">trending_up</span>
                      <span>Score: {score.toFixed(3)}</span>
                    </div>
                  )}
                </div>
              </div>

              {/* Sidebar footer */}
              <div className="px-4 py-3 border-t border-gray-100 bg-gray-50/50 shrink-0">
                <button
                  onClick={scrollToTarget}
                  className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-amber-500 text-white text-sm font-semibold hover:bg-amber-600 transition-colors shadow-sm"
                >
                  <span className="material-symbols-outlined text-[18px]">my_location</span>
                  Vai al passaggio
                </button>
              </div>
            </>
          )}
        </aside>
      </div>

      {/* ─── Stile per l'evidenziazione ─── */}
      <style>{`
        .pdf-highlight {
          background-color: rgba(251, 191, 36, 0.4) !important;
          border-radius: 2px;
          padding: 1px 0;
        }
        .react-pdf__Document {
          min-height: 100%;
        }
        .react-pdf__Page {
          background: white !important;
        }
      `}</style>
    </div>
  );
};

export default PDFViewerPage;

