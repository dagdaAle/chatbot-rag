import { useNavigate, useSearchParams } from 'react-router-dom';
import PDFReader from './pdf/PDFReader';
export default function PDFViewerPage() {
  const [params] = useSearchParams(); const navigate = useNavigate();
  return <div className="h-svh"><PDFReader selection={{ knowledgeId: params.get('kb') || '', documentId: params.get('doc') || '', pageStart: Math.max(1, Number(params.get('page')) || 1), pageEnd: Number(params.get('pageEnd')) || undefined, text: params.get('text') || '', filename: params.get('filename') || 'Documento PDF' }} onClose={() => navigate('/')} /></div>;
}
