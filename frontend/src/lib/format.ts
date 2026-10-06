export function formatTime(date: Date): string {
  return date.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('it-IT', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
}

/** Raggruppa per "Oggi", "Ieri", "Ultimi 7 giorni", "Meno recenti". */
export function groupByRecency<T extends { updated_at: string }>(items: T[]) {
  const startOfToday = new Date();
  startOfToday.setHours(0, 0, 0, 0);
  const day = 24 * 60 * 60 * 1000;
  const groups: { label: string; items: T[] }[] = [
    { label: 'Oggi', items: [] },
    { label: 'Ieri', items: [] },
    { label: 'Ultimi 7 giorni', items: [] },
    { label: 'Meno recenti', items: [] },
  ];
  for (const item of items) {
    const t = new Date(item.updated_at).getTime();
    if (t >= startOfToday.getTime()) groups[0].items.push(item);
    else if (t >= startOfToday.getTime() - day) groups[1].items.push(item);
    else if (t >= startOfToday.getTime() - 7 * day) groups[2].items.push(item);
    else groups[3].items.push(item);
  }
  return groups.filter((g) => g.items.length > 0);
}

export function errorMessage(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback;
}
