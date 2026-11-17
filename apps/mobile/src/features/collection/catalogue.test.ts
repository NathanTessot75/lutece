import type { MonumentSummary, RarityTier } from '@/db/monuments';

import { chapters, countByTier, formatNumber, numberPlaces, rows } from './catalogue';

function place(
  id: string,
  title: string,
  arrondissement: number | null,
  rarityTier: RarityTier | null = 'commun',
): MonumentSummary {
  return {
    id,
    title,
    arrondissement,
    category: null,
    century: null,
    readiness: 'ready',
    rarityTier,
  };
}

const PLACES = [
  place('vosges', 'Place des Vosges', 4, 'rare'),
  place('chapelle', 'Sainte-Chapelle', 1, 'légendaire'),
  place('eustache', 'Église Saint-Eustache', 1),
  place('bourse', 'Bourse de commerce', 1),
  place('sully', 'Hôtel de Sully', 4, 'peu_commun'),
];

describe('numberPlaces', () => {
  it('numbers the places by arrondissement, then in alphabetical order', () => {
    expect(numberPlaces(PLACES).map(({ number, monument }) => [number, monument.id])).toEqual([
      [1, 'bourse'],
      [2, 'eustache'],
      [3, 'chapelle'],
      [4, 'sully'],
      [5, 'vosges'],
    ]);
  });

  it('writes a number on three digits', () => {
    expect(formatNumber(7)).toBe('N° 007');
    expect(formatNumber(394)).toBe('N° 394');
  });
});

describe('chapters', () => {
  const entries = numberPlaces(PLACES);
  const captured = new Set(['chapelle', 'sully']);

  it('gathers the places by arrondissement, with how many are captured', () => {
    const all = chapters(entries, 'all', '', captured);
    expect(
      all.map(({ arrondissement, entries: kept, captured: count, total }) => [
        arrondissement,
        kept.length,
        count,
        total,
      ]),
    ).toEqual([
      [1, 3, 1, 3],
      [4, 2, 1, 2],
    ]);
  });

  it('keeps the places captured, or those to capture', () => {
    const ids = (filter: 'captured' | 'toCapture') =>
      chapters(entries, filter, '', captured).flatMap((chapter) =>
        chapter.entries.map((entry) => entry.monument.id),
      );
    expect(ids('captured')).toEqual(['chapelle', 'sully']);
    expect(ids('toCapture')).toEqual(['bourse', 'eustache', 'vosges']);
  });

  it('counts the places of a chapter whatever the filter', () => {
    const [first] = chapters(entries, 'toCapture', '', captured);
    expect([first.entries.length, first.captured, first.total]).toEqual([2, 1, 3]);
  });

  it('searches the names without minding accents nor case, and the numbers', () => {
    const found = (search: string) =>
      chapters(entries, 'all', search, captured).flatMap((chapter) =>
        chapter.entries.map((entry) => entry.monument.id),
      );
    expect(found('eglise')).toEqual(['eustache']);
    expect(found('  SULLY ')).toEqual(['sully']);
    expect(found('005')).toEqual(['vosges']);
    expect(found('tour')).toEqual([]);
  });
});

describe('countByTier', () => {
  it('counts the captured places of each rarity out of all', () => {
    const counts = countByTier([...PLACES, place('x', 'Sans rareté', 2, null)], new Set(['chapelle']));
    expect(counts).toEqual({
      commun: { captured: 0, total: 2 },
      peu_commun: { captured: 0, total: 1 },
      rare: { captured: 0, total: 1 },
      légendaire: { captured: 1, total: 1 },
    });
  });
});

describe('rows', () => {
  it('cuts a list into rows, the last one shorter', () => {
    expect(rows([1, 2, 3, 4, 5, 6, 7], 3)).toEqual([[1, 2, 3], [4, 5, 6], [7]]);
    expect(rows([], 3)).toEqual([]);
  });
});
