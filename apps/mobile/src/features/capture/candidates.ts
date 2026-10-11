import type { Outline } from '@/features/map/footprint';

import { type Coordinates, sight, turn } from './geometry';

/** Where the phone says the player is, and within how many metres. */
export type Fix = Coordinates & {
  accuracyM: number;
};

/** Where the phone points, and how well its compass is calibrated (0 to 3). */
export type Compass = {
  headingDeg: number;
  level: number;
};

/** A monument that can be captured, with how far it may be captured from. */
export type Target = {
  id: string;
  reachM: number;
  outlines: Outline[];
};

/** A monument within reach of the player. */
export type Candidate<T extends Target = Target> = {
  target: T;
  distanceM: number;
  /** Degrees to turn to face it, negative to the left; none without a compass. */
  offsetDeg: number | null;
  /** Whether the phone points at it, or the player stands inside it. */
  inSight: boolean;
  /** From 0 to 1, higher when nearer and better faced; 0 when not in sight. */
  score: number;
};

// SPEC §6.1: within twice the accuracy of the GPS, between 50 and 150 m.
const NEAREST_LIMIT_M = 50;
export const FURTHEST_LIMIT_M = 150;
// SPEC §6.1: the phone points at what lies within 30° plus the error of the compass.
const CONE_DEG = 30;
// The compass only tells a level of calibration; iOS documents these bounds.
const COMPASS_ERROR_DEG: Record<number, number> = { 3: 20, 2: 35, 1: 50 };
// Provisional, to be learnt from the field test set (SPEC §8): distance and
// direction weigh the same, and a monument scores half as well for its
// distance every 50 m. The distance counts in metres, not as a share of what
// is allowed: a church 30 m ahead comes before a tower 400 m behind it.
const DISTANCE_WEIGHT = 0.5;
const HALVING_DISTANCE_M = 50;

/** The distance within which a monument is a candidate. */
export function allowedDistance(accuracyM: number, reachM: number): number {
  const byAccuracy = Math.min(FURTHEST_LIMIT_M, Math.max(NEAREST_LIMIT_M, 2 * accuracyM));
  return Math.max(byAccuracy, reachM);
}

/** Half the width of what the phone points at, or none when the compass is lost. */
export function coneHalfWidth(level: number): number | null {
  const error = COMPASS_ERROR_DEG[level];
  return error === undefined ? null : CONE_DEG + error;
}

/**
 * The monuments within reach, those in sight first and the best one on top,
 * then the others from the nearest.
 */
export function findCandidates<T extends Target>(
  fix: Fix,
  compass: Compass | null,
  targets: readonly T[],
): Candidate<T>[] {
  const halfWidth = compass === null ? null : coneHalfWidth(compass.level);
  const candidates: Candidate<T>[] = [];
  for (const target of targets) {
    const { distanceM, bearingDeg } = sight(fix, target.outlines);
    const allowed = allowedDistance(fix.accuracyM, target.reachM);
    if (distanceM > allowed) {
      continue;
    }
    if (bearingDeg === null) {
      // Standing inside the monument: it is faced whichever way the phone points.
      candidates.push({ target, distanceM, offsetDeg: 0, inSight: true, score: 1 });
      continue;
    }
    const offsetDeg = compass === null ? null : turn(compass.headingDeg, bearingDeg);
    const inSight = offsetDeg !== null && halfWidth !== null && Math.abs(offsetDeg) <= halfWidth;
    const score = inSight
      ? DISTANCE_WEIGHT * (HALVING_DISTANCE_M / (HALVING_DISTANCE_M + distanceM)) +
        (1 - DISTANCE_WEIGHT) * (1 - Math.abs(offsetDeg) / halfWidth)
      : 0;
    candidates.push({ target, distanceM, offsetDeg, inSight, score });
  }
  return candidates.sort(
    (first, second) =>
      Number(second.inSight) - Number(first.inSight) ||
      second.score - first.score ||
      first.distanceM - second.distanceM,
  );
}
