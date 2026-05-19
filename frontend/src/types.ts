export const AppView = {
  CHAT: 'CHAT',
  ADMIN: 'ADMIN',
  SETTINGS: 'SETTINGS'
} as const;

export type AppView = typeof AppView[keyof typeof AppView];

export interface ChatMessage {
  id: string;
  sender: 'user' | 'ai';
  text: string;
  html?: string;
  timestamp: string;
  attachments?: {
    name: string;
    size: string;
    type: 'pdf' | 'doc' | 'image';
  }[];
  sources?: {
    filename: string;
    score: number;
    text: string;
    chunk_index: number;
    document_id: string;
  }[];
}

export interface Document {
  id: string;
  name: string;
  size: string;
  type: 'pdf' | 'docx' | 'txt';
  category: 'Corporate' | 'Technical' | 'Internal' | 'Legal';
  date: string;
  status: 'Indexed' | 'Processing' | 'Error';
}

export interface Knowledge {
  id: string;
  name: string;
  description: string;
  created_at: string;
  documents_count: number;
}
