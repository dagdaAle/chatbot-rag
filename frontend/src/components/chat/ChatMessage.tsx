import { useState } from 'react';
import { Check, Copy } from 'lucide-react';
import { Message, MessageAction, MessageActions, MessageContent } from '@/components/ui/message';
import { Button } from '@/components/ui/button';
import type { ChatSource } from '@/api/client';
import { formatTime } from '@/lib/format';
import { SourceList } from './SourceList';

export interface UiMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: ChatSource[];
  timestamp: Date;
}

export function ChatMessage({
  message,
  knowledgeId,
}: {
  message: UiMessage;
  knowledgeId: string | null;
}) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    await navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  if (message.role === 'user') {
    return (
      <Message className="justify-end">
        <MessageContent className="bg-muted max-w-[85%] rounded-3xl px-5 py-2.5 whitespace-pre-wrap sm:max-w-[75%]">
          {message.content}
        </MessageContent>
      </Message>
    );
  }

  return (
    <Message className="group flex-col items-start gap-2">
      <MessageContent
        markdown
        className="prose prose-sm dark:prose-invert w-full max-w-none bg-transparent p-0"
      >
        {message.content}
      </MessageContent>
      {message.sources && message.sources.length > 0 && (
        <SourceList sources={message.sources} knowledgeId={knowledgeId} />
      )}
      <MessageActions className="opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
        <MessageAction tooltip={copied ? 'Copiato' : 'Copia'}>
          <Button variant="ghost" size="icon" className="size-7 rounded-full" onClick={copy}>
            {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
          </Button>
        </MessageAction>
        <span className="text-muted-foreground text-xs">{formatTime(message.timestamp)}</span>
      </MessageActions>
    </Message>
  );
}
