import type { MonumentSummary } from '@/db/monuments';

export type MonumentSection = {
  /** Null gathers the monuments whose notice names no arrondissement. */
  arrondissement: number | null;
  data: MonumentSummary[];
};

/** Group the monuments by arrondissement, in alphabetical order inside each. */
export function groupByArrondissement(monuments: readonly MonumentSummary[]): MonumentSection[] {
  const groups = new Map<number | null, MonumentSummary[]>();
  for (const monument of monuments) {
    const group = groups.get(monument.arrondissement);
    if (group) {
      group.push(monument);
    } else {
      groups.set(monument.arrondissement, [monument]);
    }
  }
  return [...groups.entries()]
    .sort(([first], [second]) => (first ?? Infinity) - (second ?? Infinity))
    .map(([arrondissement, data]) => ({
      arrondissement,
      data: data.sort((first, second) => first.title.localeCompare(second.title, 'fr')),
    }));
}
