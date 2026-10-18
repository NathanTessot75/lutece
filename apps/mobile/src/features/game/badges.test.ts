import type { Groups } from '@/db/series';

import { type Played, buildBadges, evaluate, walkedKm } from './badges';

const GROUPS: Groups = {
  series: [
    { slug: 'ponts', name: 'Ponts', description: 'Les ponts.', ids: ['pont-neuf', 'pont-marie'] },
    { slug: 'vide', name: 'Vide', description: 'Rien.', ids: [] },
  ],
  arrondissements: [
    { arrondissement: 4, ids: ['pont-marie', 'notre-dame'] },
    { arrondissement: 5, ids: ['pantheon', 'arenes'] },
  ],
};

// Noon in Paris on a day of October: the sun is up.
function played(monumentId: string, changes: Partial<Played> = {}): Played {
  return {
    monumentId,
    capturedAt: '2026-10-19T10:00:00.000Z',
    latitude: 48.853,
    longitude: 2.349,
    tier: 'commun',
    arrondissement: 4,
    ...changes,
  };
}

function stateOf(slug: string, history: Played[]) {
  const state = evaluate(buildBadges(GROUPS), history).find((one) => one.badge.slug === slug);
  if (state === undefined) {
    throw new Error(`No badge ${slug}`);
  }
  return state;
}

describe('buildBadges', () => {
  it('makes a badge of each series that has places', () => {
    const slugs = buildBadges(GROUPS).map((badge) => badge.slug);
    expect(slugs).toContain('serie-ponts');
    expect(slugs).not.toContain('serie-vide');
    expect(new Set(slugs).size).toBe(slugs.length);
  });
});

describe('evaluate', () => {
  it('counts the captures towards the collection badges', () => {
    const history = [played('a'), played('b'), played('c')];
    expect(stateOf('premiere-capture', history).wonWith).toBe('a');
    expect(stateOf('flaneur', history)).toMatchObject({
      measure: { reached: 3, goal: 10 },
      wonAt: null,
    });
  });

  it('dates a badge by the capture that won it', () => {
    const history = [
      played('a', { capturedAt: '2026-10-01T10:00:00.000Z' }),
      played('b', { capturedAt: '2026-10-02T10:00:00.000Z', tier: 'légendaire' }),
      played('c', { capturedAt: '2026-10-03T10:00:00.000Z', tier: 'rare' }),
    ];
    expect(stateOf('legende', history)).toMatchObject({
      wonAt: '2026-10-02T10:00:00.000Z',
      wonWith: 'b',
    });
    expect(stateOf('hors-des-sentiers', history).wonWith).toBe('b');
  });

  it('gives the badge of a series once all its places are captured', () => {
    expect(stateOf('serie-ponts', [played('pont-neuf')]).measure).toEqual({ reached: 1, goal: 2 });
    const done = stateOf('serie-ponts', [played('pont-neuf'), played('x'), played('pont-marie')]);
    expect(done.wonWith).toBe('pont-marie');
    expect(stateOf('collectionneur', [played('pont-neuf'), played('pont-marie')]).wonWith).toBe(
      'pont-marie',
    );
  });

  it('gives the badge of an arrondissement once all its places are captured', () => {
    expect(stateOf('quartier-conquis', [played('pont-marie')]).wonAt).toBeNull();
    expect(stateOf('quartier-conquis', [played('pont-marie'), played('notre-dame')]).wonWith).toBe(
      'notre-dame',
    );
  });

  it('asks for both banks of the Seine on the same day', () => {
    const left = played('pantheon', { arrondissement: 5 });
    const right = played('notre-dame', { arrondissement: 4 });
    expect(stateOf('deux-rives', [left, right]).wonWith).toBe('notre-dame');
    const otherDay = { ...right, capturedAt: '2026-10-20T10:00:00.000Z' };
    expect(stateOf('deux-rives', [left, otherDay]).wonAt).toBeNull();
  });

  it('knows the dawn and the night of Paris', () => {
    // The sun rises at 8:20 in Paris on 19 October 2026, 6:20 UTC; it sets at 18:52.
    const dawn = played('a', { capturedAt: '2026-10-19T06:40:00.000Z' });
    const day = played('b', { capturedAt: '2026-10-19T08:00:00.000Z' });
    const night = played('c', { capturedAt: '2026-10-19T19:30:00.000Z' });
    expect(stateOf('leve-tot', [dawn]).wonWith).toBe('a');
    expect(stateOf('leve-tot', [day]).wonAt).toBeNull();
    expect(stateOf('noctambule', [day, night]).wonWith).toBe('c');
  });

  it('counts the days in a row and the seasons', () => {
    const week = ['2026-10-19', '2026-10-20', '2026-10-21', '2026-10-23'].map((day, index) =>
      played(`p${index}`, { capturedAt: `${day}T10:00:00.000Z` }),
    );
    // The gap on the 22nd breaks the run.
    expect(stateOf('une-semaine-a-paris', week).measure).toEqual({ reached: 3, goal: 7 });
    const year = ['2026-01-10', '2026-04-10', '2026-07-10', '2026-10-10'].map((day, index) =>
      played(`s${index}`, { capturedAt: `${day}T10:00:00.000Z` }),
    );
    expect(stateOf('quatre-saisons', year).wonWith).toBe('s3');
  });

  it('adds the walks between the captures of a same day only', () => {
    // About 1.1 km due north, twice the same day, then the next day.
    const north = (monumentId: string, latitude: number, day = '2026-10-19') =>
      played(monumentId, { latitude, capturedAt: `${day}T10:00:00.000Z` });
    const walks = [north('a', 48.85), north('b', 48.86), north('c', 48.87), north('d', 48.85, '2026-10-20')];
    expect(walkedKm(walks)).toBeCloseTo(2.22, 1);
    expect(stateOf('bon-marcheur', walks).measure).toEqual({ reached: 2, goal: 10 });
  });
});
