import type { SampleCandidate, SampleDecision } from '@/db/samples';
import type { Candidate, Target } from '@/features/capture/candidates';
import type { Decision } from '@/features/capture/decision';

/** The longest side, in pixels, of a kept sample: room for any model to come. */
export const SAMPLE_SIDE = 1600;
/** How far around the player the label offers monuments. */
export const LABEL_WITHIN_M = 300;

/** Every candidate within reach, as the geometry and the photo saw it. */
export function describeCandidates(
  candidates: readonly Candidate[],
  likeness: ((id: string) => number | null) | null,
): SampleCandidate[] {
  return candidates.map((candidate) => ({
    monumentId: candidate.target.id,
    distanceM: candidate.distanceM,
    offsetDeg: candidate.offsetDeg,
    inSight: candidate.inSight,
    geoScore: candidate.score,
    likeness: likeness === null ? null : likeness(candidate.target.id),
  }));
}

/** What the app would have done with the shot. */
export function describeDecision<T extends Target>(decision: Decision<T>): SampleDecision {
  switch (decision.kind) {
    case 'capture':
      return { kind: 'capture', monumentIds: [decision.candidate.target.id], reason: null };
    case 'choose':
    case 'confirm':
      return {
        kind: decision.kind,
        monumentIds: decision.candidates.map((candidate) => candidate.target.id),
        reason: null,
      };
    case 'nothing':
      return { kind: 'nothing', monumentIds: [], reason: decision.reason };
  }
}

/** The size that brings a photo within `longest` pixels; none when it already is. */
export function fitWithin(
  width: number,
  height: number,
  longest = SAMPLE_SIDE,
): { width: number; height: number } | null {
  const scale = longest / Math.max(width, height);
  if (scale >= 1) {
    return null;
  }
  return { width: Math.round(width * scale), height: Math.round(height * scale) };
}

/** A monument the player may say the photo shows. */
export type LabelChoice = {
  id: string;
  title: string;
  distanceM: number;
  /** Whether the geometry made it a candidate, and whether the phone pointed at it. */
  inReach: boolean;
  inSight: boolean;
};

/**
 * The monuments to offer as the label of a photo: those the geometry kept,
 * in sight first, then the others around, nearest first.
 */
export function labelChoices(
  candidates: readonly (Candidate & { title: string })[],
  around: readonly { id: string; title: string; distanceM: number }[],
  within = LABEL_WITHIN_M,
): LabelChoice[] {
  const kept = candidates.map((candidate) => ({
    id: candidate.target.id,
    title: candidate.title,
    distanceM: candidate.distanceM,
    inReach: true,
    inSight: candidate.inSight,
  }));
  const taken = new Set(kept.map((choice) => choice.id));
  const others = around
    .filter((monument) => !taken.has(monument.id) && monument.distanceM <= within)
    .sort((first, second) => first.distanceM - second.distanceM)
    .map((monument) => ({ ...monument, inReach: false, inSight: false }));
  return [...kept, ...others];
}
