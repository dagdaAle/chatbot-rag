import { createContext, useContext } from 'react';
import type { PDFSelection } from '@/components/pdf/PDFReader';
export const ReaderContext = createContext<{ open: (selection: PDFSelection) => void; close: () => void } | null>(null);
export function useReader() { const value = useContext(ReaderContext); if (!value) throw new Error('ReaderContext mancante'); return value; }
