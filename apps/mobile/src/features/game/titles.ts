/**
 * The titles a player earns with their points, from the first capture to the
 * whole city: the 394 places bring about 12 400 points, more with the
 * challenges of the day.
 */
export const TITLES = [
  { name: 'Badaud', from: 0 },
  { name: 'Promeneur', from: 100 },
  { name: 'Flâneur', from: 300 },
  { name: 'Arpenteur', from: 800 },
  { name: 'Chroniqueur', from: 1_600 },
  { name: 'Historien', from: 3_200 },
  { name: 'Érudit', from: 6_000 },
  { name: 'Gardien de Lutèce', from: 10_000 },
] as const;

export type Title = (typeof TITLES)[number];

export type TitleStanding = {
  title: Title;
  /** The title after, none at the last. */
  next: Title | null;
  /** How far towards the next title, from 0 to 1; 1 at the last. */
  progress: number;
};

/** The title of a player with these points, and how far they are from the next. */
export function titleFor(points: number): TitleStanding {
  const index = TITLES.findLastIndex((title) => points >= title.from);
  const title = TITLES[Math.max(index, 0)];
  const next = TITLES[index + 1] ?? null;
  if (next === null) {
    return { title, next, progress: 1 };
  }
  return { title, next, progress: (points - title.from) / (next.from - title.from) };
}
