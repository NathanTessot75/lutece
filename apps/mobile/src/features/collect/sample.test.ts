import type { Candidate, Target } from '@/features/capture/candidates';
import type { Scored } from '@/features/capture/decision';

import { describeCandidates, describeDecision, fitWithin, labelChoices } from './sample';

function candidate(id: string, distanceM: number, inSight = true): Candidate {
  const target: Target = { id, reachM: 0, outlines: [] };
  return { target, distanceM, offsetDeg: inSight ? 4 : 70, inSight, score: inSight ? 0.6 : 0 };
}

function scored(id: string): Scored {
  return { ...candidate(id, 20), likeness: 0.7 };
}

describe('describeCandidates', () => {
  it('keeps every candidate within reach, with its likeness', () => {
    const looks = (id: string) => (id === 'church' ? 0.71 : null);
    expect(describeCandidates([candidate('church', 30), candidate('shop', 80, false)], looks)).toEqual([
      { monumentId: 'church', distanceM: 30, offsetDeg: 4, inSight: true, geoScore: 0.6, likeness: 0.71 },
      { monumentId: 'shop', distanceM: 80, offsetDeg: 70, inSight: false, geoScore: 0, likeness: null },
    ]);
    expect(describeCandidates([candidate('church', 30)], null)[0].likeness).toBeNull();
  });
});

describe('describeDecision', () => {
  it('names what the app would have captured, offered or refused', () => {
    expect(describeDecision({ kind: 'capture', candidate: scored('church') })).toEqual({
      kind: 'capture',
      monumentIds: ['church'],
      reason: null,
    });
    expect(
      describeDecision({ kind: 'choose', candidates: [scored('church'), scored('chapel')] }),
    ).toEqual({ kind: 'choose', monumentIds: ['church', 'chapel'], reason: null });
    expect(describeDecision({ kind: 'nothing', reason: 'not_recognised' })).toEqual({
      kind: 'nothing',
      monumentIds: [],
      reason: 'not_recognised',
    });
  });
});

describe('fitWithin', () => {
  it('brings the longest side down to the size kept, never up', () => {
    expect(fitWithin(4032, 3024)).toEqual({ width: 1600, height: 1200 });
    expect(fitWithin(3024, 4032)).toEqual({ width: 1200, height: 1600 });
    expect(fitWithin(1200, 900)).toBeNull();
    expect(fitWithin(1600, 1000)).toBeNull();
  });
});

describe('labelChoices', () => {
  it('offers the candidates first, then the monuments around, nearest first', () => {
    const candidates = [
      { ...candidate('church', 40), title: 'Église' },
      { ...candidate('tower', 600, false), title: 'Tour' },
    ];
    const around = [
      { id: 'museum', title: 'Musée', distanceM: 250 },
      { id: 'church', title: 'Église', distanceM: 40 },
      { id: 'fountain', title: 'Fontaine', distanceM: 120 },
      { id: 'far', title: 'Loin', distanceM: 450 },
    ];
    expect(labelChoices(candidates, around).map((choice) => choice.id)).toEqual([
      'church',
      'tower',
      'fountain',
      'museum',
    ]);
    const [church, , fountain] = labelChoices(candidates, around);
    expect(church).toMatchObject({ inReach: true, inSight: true });
    expect(fountain).toMatchObject({ inReach: false, inSight: false, distanceM: 120 });
  });
});
