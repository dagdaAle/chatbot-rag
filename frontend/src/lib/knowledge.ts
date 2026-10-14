import type { KnowledgePermission, KnowledgeVisibility } from '@/api/client';

export const selectClass = 'border-input bg-background h-9 rounded-md border px-3 text-sm';

export const visibilityLabel: Record<KnowledgeVisibility, string> = {
  private: 'Riservata',
  organization: 'Tutta l’organizzazione',
};

export const permissionLabel: Record<KnowledgePermission, string> = {
  owner: 'Proprietario',
  editor: 'Editor',
  viewer: 'Lettore',
};
