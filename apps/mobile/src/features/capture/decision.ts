import type { Candidate, Target } from './candidates';

/** Why pressing the shutter captures nothing. */
export type Refusal = 'out_of_reach' | 'not_facing' | 'compass_lost' | 'already_captured';

/** What pressing the shutter does. */
export type Decision<T extends Target = Target> =
  | { kind: 'capture'; candidate: Candidate<T> }
  | { kind: 'choose'; candidates: Candidate<T>[] }
  | { kind: 'nothing'; reason: Refusal };

// Provisional, to be set from the field tests: the first candidate is taken
// without asking when it scores this much above the second.
const CLEAR_LEAD = 0.15;
const MAX_CHOICES = 3;

/**
 * Decide from the candidates, best first, which monument a shot captures:
 * the one that stands out, or the one the player will pick among a few.
 */
export function decide<T extends Target>(
  candidates: readonly Candidate<T>[],
  captured: ReadonlySet<string>,
  compassWorks: boolean,
): Decision<T> {
  const inSight = candidates.filter((candidate) => candidate.inSight);
  const open = inSight.filter((candidate) => !captured.has(candidate.target.id));
  if (open.length === 0) {
    if (inSight.length > 0) {
      return { kind: 'nothing', reason: 'already_captured' };
    }
    if (candidates.length === 0) {
      return { kind: 'nothing', reason: 'out_of_reach' };
    }
    return { kind: 'nothing', reason: compassWorks ? 'not_facing' : 'compass_lost' };
  }
  const [first, second] = open;
  if (second === undefined || first.score - second.score >= CLEAR_LEAD) {
    return { kind: 'capture', candidate: first };
  }
  return { kind: 'choose', candidates: open.slice(0, MAX_CHOICES) };
}
