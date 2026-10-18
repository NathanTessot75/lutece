import type { Groups } from '@/db/series';

import { advancesOf, countProgress, formatProgress, isComplete } from './progress';

const GROUPS: Groups = {
  series: [
    { slug: 'ponts', name: 'Ponts', description: 'Les ponts.', ids: ['pont-neuf', 'pont-marie'] },
    { slug: 'gares', name: 'Gares', description: 'Les gares.', ids: ['gare-du-nord'] },
    { slug: 'quais', name: 'Quais', description: 'Les quais.', ids: ['pont-neuf', 'quai'] },
  ],
  arrondissements: [
    { arrondissement: 1, ids: ['pont-neuf', 'louvre'] },
    { arrondissement: 4, ids: ['pont-marie'] },
  ],
};

describe('countProgress', () => {
  it('counts the places captured among those of a group', () => {
    const captured = new Set(['pont-neuf', 'louvre']);
    expect(countProgress(['pont-neuf', 'pont-marie'], captured)).toEqual({ captured: 1, total: 2 });
    expect(formatProgress({ captured: 1, total: 2 })).toBe('1/2');
  });

  it('calls a group complete when all its places are captured', () => {
    expect(isComplete({ captured: 2, total: 2 })).toBe(true);
    expect(isComplete({ captured: 1, total: 2 })).toBe(false);
    // An empty group is never complete.
    expect(isComplete({ captured: 0, total: 0 })).toBe(false);
  });
});

describe('advancesOf', () => {
  it('gives the series of a monument, then its arrondissement', () => {
    const captured = new Set(['pont-neuf']);
    expect(advancesOf({ id: 'pont-neuf', arrondissement: 1 }, GROUPS, captured)).toEqual([
      { kind: 'series', key: 'ponts', label: 'Ponts', progress: { captured: 1, total: 2 } },
      { kind: 'series', key: 'quais', label: 'Quais', progress: { captured: 1, total: 2 } },
      {
        kind: 'arrondissement',
        key: '1',
        label: '1er arrondissement',
        progress: { captured: 1, total: 2 },
      },
    ]);
  });

  it('gives nothing for a monument in no group', () => {
    expect(advancesOf({ id: 'ailleurs', arrondissement: null }, GROUPS, new Set())).toEqual([]);
  });
});
