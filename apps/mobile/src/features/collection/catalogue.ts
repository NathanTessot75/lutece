import type { MonumentSummary, RarityTier } from '@/db/monuments';
import { groupByArrondissement } from '@/features/monuments/sections';

/** A place of the catalogue, with its number. */
export type Entry = {
  number: number;
  monument: MonumentSummary;
};

/** The places of an arrondissement that are kept, with how many it holds and how many of them are captured. */
export type Chapter = {
  arrondissement: number | null;
  entries: Entry[];
  captured: number;
  total: number;
};

export type Filter = 'all' | 'captured' | 'toCapture';

type Captured = { has: (id: string) => boolean };

/**
 * Number every place, like a catalogue: by arrondissement, from the 1st to
 * the 20th, then in alphabetical order. The numbers follow the places of the
 * bundle: a place added or removed shifts those after it.
 */
export function numberPlaces(monuments: readonly MonumentSummary[]): Entry[] {
  return groupByArrondissement(monuments)
    .flatMap((section) => section.data)
    .map((monument, index) => ({ number: index + 1, monument }));
}

/** 7 → « N° 007 ». */
export function formatNumber(number: number): string {
  return `N° ${String(number).padStart(3, '0')}`;
}

/** Lower case and without accents, to search as one types. */
function folded(text: string): string {
  return text
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLocaleLowerCase('fr');
}

/** The entries that the filter and the search keep, by arrondissement. */
export function chapters(
  entries: readonly Entry[],
  filter: Filter,
  search: string,
  captured: Captured,
): Chapter[] {
  const wanted = folded(search.trim());
  const byArrondissement = new Map<number | null, Chapter>();
  for (const entry of entries) {
    const { monument } = entry;
    const chapter = byArrondissement.get(monument.arrondissement) ?? {
      arrondissement: monument.arrondissement,
      entries: [],
      captured: 0,
      total: 0,
    };
    byArrondissement.set(monument.arrondissement, chapter);
    chapter.total += 1;
    const isCaptured = captured.has(monument.id);
    if (isCaptured) {
      chapter.captured += 1;
    }
    const kept =
      (filter === 'all' || (filter === 'captured') === isCaptured) &&
      (wanted === '' ||
        folded(monument.title).includes(wanted) ||
        formatNumber(entry.number).includes(wanted));
    if (kept) {
      chapter.entries.push(entry);
    }
  }
  return [...byArrondissement.values()].filter((chapter) => chapter.entries.length > 0);
}

/** For each tier of rarity, how many places are captured, out of how many. */
export function countByTier(
  monuments: readonly MonumentSummary[],
  captured: Captured,
): Record<RarityTier, { captured: number; total: number }> {
  const counts: Record<RarityTier, { captured: number; total: number }> = {
    commun: { captured: 0, total: 0 },
    peu_commun: { captured: 0, total: 0 },
    rare: { captured: 0, total: 0 },
    légendaire: { captured: 0, total: 0 },
  };
  for (const monument of monuments) {
    if (monument.rarityTier === null) {
      continue;
    }
    counts[monument.rarityTier].total += 1;
    if (captured.has(monument.id)) {
      counts[monument.rarityTier].captured += 1;
    }
  }
  return counts;
}

/** Cut a list into rows of a given length, the last one shorter. */
export function rows<T>(items: readonly T[], length: number): T[][] {
  const cut: T[][] = [];
  for (let start = 0; start < items.length; start += length) {
    cut.push(items.slice(start, start + length));
  }
  return cut;
}
