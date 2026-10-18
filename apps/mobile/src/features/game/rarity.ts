import type { RarityTier } from '@/db/monuments';
import { formatCount } from '@/lib/format';

/** The points that a capture brings, by tier (decision of 18 October 2026). */
const POINTS: Record<RarityTier, number> = {
  commun: 10,
  peu_commun: 25,
  rare: 50,
  légendaire: 100,
};

const LABELS: Record<RarityTier, string> = {
  commun: 'Commun',
  peu_commun: 'Peu commun',
  rare: 'Rare',
  légendaire: 'Légendaire',
};

// What a tier means, for the tiers that deserve a word at the capture.
const NOTES: Partial<Record<RarityTier, string>> = {
  rare: 'Un lieu que peu de gens connaissent.',
  légendaire: 'L’un des lieux les moins connus de Lutèce.',
};

/** The points of a capture; a place that the pipeline did not rate counts as common. */
export function pointsFor(tier: RarityTier | null): number {
  return POINTS[tier ?? 'commun'];
}

export function tierLabel(tier: RarityTier): string {
  return LABELS[tier];
}

export function tierNote(tier: RarityTier | null): string | null {
  return tier === null ? null : (NOTES[tier] ?? null);
}

/** 1 → « 1 point », 1250 → « 1 250 points ». */
export function formatPoints(points: number): string {
  return `${formatCount(points)} ${points > 1 ? 'points' : 'point'}`;
}

/** All that the captures brought; a capture from before the points brings none yet. */
export function totalPoints(captures: readonly { points: number | null }[]): number {
  return captures.reduce((sum, capture) => sum + (capture.points ?? 0), 0);
}
