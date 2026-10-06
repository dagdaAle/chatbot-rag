import { ChevronDown, ExternalLink, FileText } from 'lucide-react';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/ui/hover-card';
import { Badge } from '@/components/ui/badge';
import { getPDFViewerUrl, type ChatSource } from '@/api/client';

function pages(s: ChatSource): string {
  const start = s.page_start ?? 1;
  const end = s.page_end ?? start;
  return start === end ? `p. ${start}` : `pp. ${start}–${end}`;
}

export function SourceList({
  sources,
  knowledgeId,
}: {
  sources: ChatSource[];
  knowledgeId: string | null;
}) {
  if (sources.length === 0) return null;

  return (
    <Collapsible className="w-full">
      <CollapsibleTrigger className="text-muted-foreground hover:text-foreground group flex items-center gap-1.5 text-xs font-medium transition-colors">
        <FileText className="size-3.5" />
        {sources.length} {sources.length === 1 ? 'fonte' : 'fonti'}
        <ChevronDown className="size-3.5 transition-transform group-data-[state=open]:rotate-180" />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <ol className="mt-2 flex flex-wrap gap-1.5">
          {sources.map((s, i) => {
            const sourceKnowledgeId = s.knowledge_id ?? knowledgeId;
            const href = sourceKnowledgeId
              ? getPDFViewerUrl({
                  knowledgeId: sourceKnowledgeId,
                  documentId: s.document_id,
                  pageStart: s.page_start ?? 1,
                  pageEnd: s.page_end,
                  text: s.text.slice(0, 500),
                  filename: s.filename,
                  score: s.score,
                })
              : null;
            return (
              <li key={`${s.document_id}-${s.chunk_index}`}>
                <HoverCard openDelay={150} closeDelay={50}>
                  <HoverCardTrigger asChild>
                    <a
                      href={href ?? undefined}
                      target="_blank"
                      rel="noreferrer"
                      aria-disabled={!href}
                      className="bg-muted hover:bg-accent inline-flex max-w-64 items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors"
                    >
                      <span className="text-muted-foreground font-mono">{i + 1}</span>
                      <span className="truncate">{s.filename}</span>
                      <span className="text-muted-foreground shrink-0">{pages(s)}</span>
                    </a>
                  </HoverCardTrigger>
                  <HoverCardContent className="w-96" align="start">
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <p className="truncate text-sm font-medium">{s.filename}</p>
                      <Badge variant="secondary" title="Similarità con la domanda">
                        {Math.round(s.score * 100)}%
                      </Badge>
                    </div>
                    <p className="text-muted-foreground line-clamp-[10] text-xs leading-relaxed whitespace-pre-line">
                      {s.text}
                    </p>
                    {href && (
                      <p className="text-primary mt-2 flex items-center gap-1 text-xs">
                        <ExternalLink className="size-3" /> Clic per aprire il PDF a {pages(s)}
                      </p>
                    )}
                  </HoverCardContent>
                </HoverCard>
              </li>
            );
          })}
        </ol>
      </CollapsibleContent>
    </Collapsible>
  );
}
