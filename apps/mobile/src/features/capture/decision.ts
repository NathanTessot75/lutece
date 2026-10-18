import type { Candidate, Target } from './candidates';

/** Why pressing the shutter captures nothing. */
export type Refusal =
  | 'out_of_reach'
  | 'not_facing'
  | 'compass_lost'
  | 'already_captured'
  | 'not_recognised'
  | 'too_far_without_photo';

/** A candidate with how much the photo looks like it; none without a reference photo. */
export type Scored<T extends Target = Target> = Candidate<T> & {
  likeness: number | null;
};

/** What a shot does once the photo is looked at. */
export type Decision<T extends Target = Target> =
  | { kind: 'capture'; candidate: Scored<T> }
  | { kind: 'choose'; candidates: Scored<T>[] }
  | { kind: 'confirm'; candidates: Scored<T>[] }
  | { kind: 'nothing'; reason: Refusal };

// Provisional, from the reference photos played as captures (pipeline README,
// « La capture avec l'image »), to be set again from photos taken in the street.
// Under this likeness, the photo shows none of the candidates: 4.1 % of the
// photos that show their place fall under it.
export const RECOGNISED_FROM = 0.42;
// The first candidate is taken without asking when the photo looks this much
// more like it than like the second: right 97 times in 100.
export const CLEAR_LEAD = 0.1;
// SPEC §6.3: what the photo cannot vouch for is captured from close by only,
// and once the player has confirmed it.
export const UNSEEN_WITHIN_M = 30;
const MAX_CHOICES = 3;

/**
 * Whether pressing the shutter is worth a photo: something to capture must be
 * in sight. The geometry alone tells, before the camera is asked anything.
 */
export function refuseBeforePhoto<T extends Target>(
  candidates: readonly Candidate<T>[],
  captured: { has: (id: string) => boolean },
  compassWorks: boolean,
): Refusal | null {
  const inSight = candidates.filter((candidate) => candidate.inSight);
  if (inSight.some((candidate) => !captured.has(candidate.target.id))) {
    return null;
  }
  if (inSight.length > 0) {
    return 'already_captured';
  }
  if (candidates.length === 0) {
    return 'out_of_reach';
  }
  return compassWorks ? 'not_facing' : 'compass_lost';
}

/** How much the photo looks like a candidate; nothing without a reference photo. */
function looks(candidate: Scored): number {
  return candidate.likeness ?? -1;
}

/** What cannot be recognised on the photo: captured from close by, once confirmed. */
function closeByOnly<T extends Target>(
  unseen: readonly Scored<T>[],
  refusal: Refusal,
): Decision<T> {
  const near = unseen.filter((candidate) => candidate.distanceM <= UNSEEN_WITHIN_M);
  if (near.length === 0) {
    return { kind: 'nothing', reason: refusal };
  }
  return { kind: 'confirm', candidates: near.slice(0, MAX_CHOICES) };
}

/**
 * Decide which monument a shot captures. The geometry has chosen the
 * candidates, best first; the photo tells them apart. `likeness` is `null`
 * when there is no photo to look at.
 */
export function decideShot<T extends Target>(
  candidates: readonly Candidate<T>[],
  likeness: ((id: string) => number | null) | null,
  captured: { has: (id: string) => boolean },
): Decision<T> {
  const inSight: Scored<T>[] = candidates
    .filter((candidate) => candidate.inSight)
    .map((candidate) => ({
      ...candidate,
      likeness: likeness === null ? null : likeness(candidate.target.id),
    }));
  const open = inSight.filter((candidate) => !captured.has(candidate.target.id));
  if (likeness === null) {
    // Without a photo, the geometry is all there is.
    return closeByOnly(open, 'too_far_without_photo');
  }

  const recognised = inSight
    .filter((candidate) => looks(candidate) >= RECOGNISED_FROM)
    .sort((first, second) => looks(second) - looks(first));
  const best = recognised.find((candidate) => !captured.has(candidate.target.id));
  // A monument already captured that the photo shows more than any other.
  const rival = recognised[0] !== best ? recognised[0] : undefined;
  if (rival !== undefined && (best === undefined || looks(rival) - looks(best) >= CLEAR_LEAD)) {
    return { kind: 'nothing', reason: 'already_captured' };
  }
  if (best === undefined) {
    // No reference photo matches: only a place without one may still be meant.
    return closeByOnly(
      open.filter((candidate) => candidate.likeness === null),
      'not_recognised',
    );
  }
  const close = recognised.filter(
    (candidate) =>
      !captured.has(candidate.target.id) && looks(best) - looks(candidate) < CLEAR_LEAD,
  );
  if (close.length > 1) {
    return { kind: 'choose', candidates: close.slice(0, MAX_CHOICES) };
  }
  // Taken without asking, unless a monument already captured looks almost as much like it.
  return rival === undefined
    ? { kind: 'capture', candidate: best }
    : { kind: 'confirm', candidates: [best] };
}
