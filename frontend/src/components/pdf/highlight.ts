export function normalized(text: string) {
  return text.normalize('NFKC').toLocaleLowerCase('it').replace(/[^\p{L}\p{N}]/gu, '');
}
export function matchingRanges(pageText: string, source: string): [number, number][] {
  const page = normalized(pageText), needle = normalized(source);
  if (needle.length < 8) return [];
  const ranges: [number, number][] = [];
  const exact = page.indexOf(needle);
  if (exact >= 0) return [[exact, exact + needle.length]];
  const size = Math.min(60, needle.length);
  for (let offset = 0; offset <= needle.length - size; offset += Math.max(1, Math.floor(size / 2))) {
    const fragment = needle.slice(offset, offset + size);
    let index = page.indexOf(fragment);
    while (index >= 0) {
      ranges.push([index, index + size]);
      index = page.indexOf(fragment, index + size);
    }
  }
  return ranges;
}
export function renderHighlighted(text: string, offset: number, ranges: [number, number][]) {
  const escape = (str: string) => str.replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]!));
  let index = offset, output = '', buffer = '', marked = false;
  for (const char of text) {
    const length = normalized(char).length;
    const next: boolean = length > 0 ? ranges.some(([start, end]) => index < end && index + length > start) : marked;
    if (next !== marked) {
      output += marked ? `<mark class="pdf-highlight">${escape(buffer)}</mark>` : escape(buffer);
      buffer = ''; marked = next;
    }
    buffer += char; index += length;
  }
  return output + (marked ? `<mark class="pdf-highlight">${escape(buffer)}</mark>` : escape(buffer));
}
