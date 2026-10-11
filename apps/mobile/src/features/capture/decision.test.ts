import type { Candidate, Target } from './candidates';
import { decide } from './decision';

function candidate(id: string, score: number, inSight = true): Candidate {
  const target: Target = { id, reachM: 0, outlines: [] };
  return { target, distanceM: 20, offsetDeg: 0, inSight, score: inSight ? score : 0 };
}

const NONE = new Set<string>();

function chosen(decision: ReturnType<typeof decide>): string[] {
  if (decision.kind === 'capture') {
    return [decision.candidate.target.id];
  }
  return decision.kind === 'choose' ? decision.candidates.map(({ target }) => target.id) : [];
}

describe('decide', () => {
  it('captures the only monument in sight', () => {
    const decision = decide([candidate('church', 0.6), candidate('shop', 0, false)], NONE, true);
    expect(decision.kind).toBe('capture');
    expect(chosen(decision)).toEqual(['church']);
  });

  it('captures the monument that stands out', () => {
    const decision = decide([candidate('church', 0.8), candidate('shop', 0.65)], NONE, true);
    expect(decision.kind).toBe('capture');
    expect(chosen(decision)).toEqual(['church']);
  });

  it('asks the player when two monuments are close', () => {
    const decision = decide([candidate('church', 0.8), candidate('shop', 0.66)], NONE, true);
    expect(decision.kind).toBe('choose');
    expect(chosen(decision)).toEqual(['church', 'shop']);
  });

  it('offers three monuments at most, the best ones', () => {
    const crowd = ['a', 'b', 'c', 'd'].map((id, index) => candidate(id, 0.8 - index * 0.01));
    expect(chosen(decide(crowd, NONE, true))).toEqual(['a', 'b', 'c']);
  });

  it('leaves out the monuments already captured', () => {
    const candidates = [candidate('church', 0.8), candidate('shop', 0.78), candidate('inn', 0.5)];
    const decision = decide(candidates, new Set(['church']), true);
    // The shop now stands out from the inn.
    expect(decision.kind).toBe('capture');
    expect(chosen(decision)).toEqual(['shop']);
  });

  it.each([
    ['nothing is within reach', [], NONE, true, 'out_of_reach'],
    ['nothing is faced', [candidate('shop', 0, false)], NONE, true, 'not_facing'],
    ['the compass is lost', [candidate('shop', 0, false)], NONE, false, 'compass_lost'],
    [
      'what is faced is already captured',
      [candidate('church', 0.8), candidate('shop', 0, false)],
      new Set(['church']),
      true,
      'already_captured',
    ],
  ] as const)('captures nothing when %s', (_, candidates, captured, compassWorks, reason) => {
    expect(decide(candidates, captured, compassWorks)).toEqual({ kind: 'nothing', reason });
  });
});
