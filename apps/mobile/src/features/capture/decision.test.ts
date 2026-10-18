import type { Candidate, Target } from './candidates';
import { type Decision, decideShot, refuseBeforePhoto } from './decision';

function candidate(id: string, score: number, distanceM = 20, inSight = true): Candidate {
  const target: Target = { id, reachM: 0, outlines: [] };
  return { target, distanceM, offsetDeg: 0, inSight, score: inSight ? score : 0 };
}

const NONE = new Set<string>();

/** How much the photo looks like each monument; the others have no reference photo. */
function photo(likeness: Record<string, number>): (id: string) => number | null {
  return (id) => likeness[id] ?? null;
}

function ids(decision: Decision): string[] {
  switch (decision.kind) {
    case 'capture':
      return [decision.candidate.target.id];
    case 'choose':
    case 'confirm':
      return decision.candidates.map((choice) => choice.target.id);
    case 'nothing':
      return [];
  }
}

describe('refuseBeforePhoto', () => {
  it('lets the photo be taken when something to capture is in sight', () => {
    expect(refuseBeforePhoto([candidate('church', 0.6)], NONE, true)).toBeNull();
    expect(
      refuseBeforePhoto([candidate('church', 0.6), candidate('inn', 0.5)], new Set(['church']), true),
    ).toBeNull();
  });

  it.each([
    ['nothing is within reach', [], NONE, true, 'out_of_reach'],
    ['nothing is faced', [candidate('shop', 0, 20, false)], NONE, true, 'not_facing'],
    ['the compass is lost', [candidate('shop', 0, 20, false)], NONE, false, 'compass_lost'],
    [
      'all that is faced is already captured',
      [candidate('church', 0.8), candidate('shop', 0, 20, false)],
      new Set(['church']),
      true,
      'already_captured',
    ],
  ] as const)('refuses when %s', (_, candidates, captured, compassWorks, reason) => {
    expect(refuseBeforePhoto(candidates, captured, compassWorks)).toBe(reason);
  });
});

describe('decideShot', () => {
  it('captures what the photo shows, whatever the geometry preferred', () => {
    const candidates = [candidate('church', 0.9), candidate('tower', 0.3, 400)];
    const decision = decideShot(candidates, photo({ church: 0.35, tower: 0.71 }), NONE);
    expect(decision.kind).toBe('capture');
    expect(ids(decision)).toEqual(['tower']);
    expect(decision.kind === 'capture' && decision.candidate.likeness).toBe(0.71);
  });

  it('refuses when the photo shows none of the monuments in sight', () => {
    // From rue Soufflot: the lycée is within reach and in the axis, the photo
    // shows the street.
    const decision = decideShot([candidate('lycee', 0.6, 250)], photo({ lycee: 0.24 }), NONE);
    expect(decision).toEqual({ kind: 'nothing', reason: 'not_recognised' });
  });

  it('asks when the photo looks almost as much like two monuments', () => {
    const candidates = [candidate('church', 0.8), candidate('chapel', 0.7), candidate('inn', 0.5)];
    const decision = decideShot(candidates, photo({ church: 0.62, chapel: 0.68, inn: 0.4 }), NONE);
    expect(decision.kind).toBe('choose');
    // The best likeness first; the inn, unrecognised, is not offered.
    expect(ids(decision)).toEqual(['chapel', 'church']);
  });

  it('offers three monuments at most', () => {
    const crowd = ['a', 'b', 'c', 'd'].map((id) => candidate(id, 0.5));
    const decision = decideShot(crowd, photo({ a: 0.7, b: 0.69, c: 0.68, d: 0.67 }), NONE);
    expect(ids(decision)).toEqual(['a', 'b', 'c']);
  });

  it('says so when the photo shows a monument already captured', () => {
    const candidates = [candidate('church', 0.8), candidate('inn', 0.5)];
    const captured = new Set(['church']);
    expect(decideShot(candidates, photo({ church: 0.8, inn: 0.45 }), captured)).toEqual({
      kind: 'nothing',
      reason: 'already_captured',
    });
    expect(decideShot(candidates, photo({ church: 0.8, inn: 0.3 }), captured).kind).toBe('nothing');
    // Almost as like: the player confirms the other one.
    const close = decideShot(candidates, photo({ church: 0.62, inn: 0.58 }), captured);
    expect(close.kind).toBe('confirm');
    expect(ids(close)).toEqual(['inn']);
    // Far behind: the other one is taken.
    const clear = decideShot(candidates, photo({ church: 0.3, inn: 0.66 }), captured);
    expect(clear.kind).toBe('capture');
    expect(ids(clear)).toEqual(['inn']);
  });

  it('captures a place without a reference photo from close by, once confirmed', () => {
    const near = decideShot([candidate('kiosk', 0.7, 25)], photo({}), NONE);
    expect(near.kind).toBe('confirm');
    expect(ids(near)).toEqual(['kiosk']);
    expect(decideShot([candidate('kiosk', 0.7, 60)], photo({}), NONE)).toEqual({
      kind: 'nothing',
      reason: 'not_recognised',
    });
    // A monument that the photo shows comes first.
    const both = decideShot(
      [candidate('kiosk', 0.8, 10), candidate('church', 0.6, 40)],
      photo({ church: 0.66 }),
      NONE,
    );
    expect(ids(both)).toEqual(['church']);
  });

  it('without a photo, captures from close by only, once confirmed', () => {
    const candidates = [candidate('church', 0.8, 18), candidate('chapel', 0.7, 28), candidate('tower', 0.6, 90)];
    const decision = decideShot(candidates, null, NONE);
    expect(decision.kind).toBe('confirm');
    expect(ids(decision)).toEqual(['church', 'chapel']);
    expect(decideShot([candidate('tower', 0.6, 90)], null, NONE)).toEqual({
      kind: 'nothing',
      reason: 'too_far_without_photo',
    });
  });

  it('leaves aside what is not in sight', () => {
    const candidates = [candidate('church', 0.7), candidate('shop', 0, 10, false)];
    const decision = decideShot(candidates, photo({ church: 0.5, shop: 0.9 }), NONE);
    expect(ids(decision)).toEqual(['church']);
  });
});
