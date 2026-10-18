import type { Groups } from '@/db/series';
import { formatArrondissement } from '@/lib/format';

/** How many places of a group the player has captured, out of how many. */
export type Progress = {
  captured: number;
  total: number;
};

/** A group that a monument belongs to, and where the player is in it. */
export type Advance = {
  kind: 'series' | 'arrondissement';
  /** The slug of a series, or the number of an arrondissement. */
  key: string;
  label: string;
  progress: Progress;
};

type Captured = { has: (id: string) => boolean };

export function countProgress(ids: readonly string[], captured: Captured): Progress {
  return { captured: ids.filter((id) => captured.has(id)).length, total: ids.length };
}

export function isComplete(progress: Progress): boolean {
  return progress.total > 0 && progress.captured === progress.total;
}

/** « 3/12 ». */
export function formatProgress(progress: Progress): string {
  return `${progress.captured}/${progress.total}`;
}

/** The series of a monument, then its arrondissement, with the player's progress in each. */
export function advancesOf(
  monument: { id: string; arrondissement: number | null },
  groups: Groups,
  captured: Captured,
): Advance[] {
  const advances: Advance[] = groups.series
    .filter((series) => series.ids.includes(monument.id))
    .map((series) => ({
      kind: 'series',
      key: series.slug,
      label: series.name,
      progress: countProgress(series.ids, captured),
    }));
  const home = groups.arrondissements.find(
    (group) => group.arrondissement === monument.arrondissement,
  );
  if (home !== undefined) {
    advances.push({
      kind: 'arrondissement',
      key: String(home.arrondissement),
      label: formatArrondissement(home.arrondissement),
      progress: countProgress(home.ids, captured),
    });
  }
  return advances;
}
