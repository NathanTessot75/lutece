import type { RarityTier } from '@/db/monuments';
import type { Groups } from '@/db/series';
import { distanceBetween } from '@/features/capture/geometry';

import { sunTimes } from './sun';
import { daysBetween, parisDay, seasonOf } from './time';

export type BadgeFamily = 'collection' | 'rarete' | 'paris' | 'series' | 'moments' | 'marche';

/** The families of badges, in the order the badge book shows them. */
export const FAMILIES: readonly { family: BadgeFamily; name: string }[] = [
  { family: 'collection', name: 'Collection' },
  { family: 'rarete', name: 'Rareté' },
  { family: 'paris', name: 'Paris' },
  { family: 'series', name: 'Séries' },
  { family: 'moments', name: 'Moments' },
  { family: 'marche', name: 'Marche' },
];

/** A capture as the badges see it. */
export type Played = {
  monumentId: string;
  capturedAt: string;
  latitude: number;
  longitude: number;
  tier: RarityTier | null;
  arrondissement: number | null;
};

/** How far the captures go towards a badge: won once `reached` comes to `goal`. */
export type Measure = { reached: number; goal: number };

/**
 * A badge. Its measure only grows as captures are added: the capture that
 * won it is the first one after which the goal is reached.
 */
export type Badge = {
  slug: string;
  family: BadgeFamily;
  name: string;
  condition: string;
  /** Temporary emoji, to be replaced (decision of 19 October 2026). */
  icon: string;
  /** What `reached` counts, when it is not captures or places. */
  unit?: string;
  measure: (played: readonly Played[]) => Measure;
};

export type BadgeState = {
  badge: Badge;
  measure: Measure;
  /** When the capture that won it was made; none until it is won. */
  wonAt: string | null;
  /** The monument of that capture. */
  wonWith: string | null;
};

// The arrondissements wholly south of the Seine.
const LEFT_BANK = new Set([5, 6, 7, 13, 14, 15]);
const DAWN_MS = 60 * 60_000;

const SERIES_ICONS: Record<string, string> = {
  ponts: '🌉',
  fontaines: '⛲',
  'passages-couverts': '🏬',
  gares: '🚉',
  'places-et-jardins': '🌳',
  eglises: '⛪',
  cultes: '🕍',
  couvents: '📿',
  'hotels-particuliers': '🏰',
  'hotels-du-marais': '🗝️',
  theatres: '🎭',
  'cabarets-et-salles': '🎬',
  cafes: '☕',
  'grands-magasins': '🛍️',
  musees: '🖼️',
  'monuments-et-statues': '🗽',
  'portes-et-barrieres': '🚪',
  ecoles: '🎓',
  hopitaux: '🏥',
  stades: '🏟️',
  cimetieres: '🪦',
};

function atLeast(goal: number, count: (played: readonly Played[]) => number) {
  return (played: readonly Played[]): Measure => ({ reached: Math.min(count(played), goal), goal });
}

function whether(test: (played: readonly Played[]) => boolean) {
  return (played: readonly Played[]): Measure => ({ reached: test(played) ? 1 : 0, goal: 1 });
}

function byDay(played: readonly Played[]): Map<string, Played[]> {
  const days = new Map<string, Played[]>();
  for (const capture of played) {
    const day = parisDay(capture.capturedAt);
    days.set(day, [...(days.get(day) ?? []), capture]);
  }
  return days;
}

function longestStreak(played: readonly Played[]): number {
  const days = [...byDay(played).keys()].sort();
  let longest = 0;
  let current = 0;
  days.forEach((day, index) => {
    current = index > 0 && daysBetween(days[index - 1], day) === 1 ? current + 1 : 1;
    longest = Math.max(longest, current);
  });
  return longest;
}

/** Kilometres from capture to capture within each day, as the crow flies. */
export function walkedKm(played: readonly Played[]): number {
  let metres = 0;
  for (const captures of byDay(played).values()) {
    for (let index = 1; index < captures.length; index++) {
      metres += distanceBetween(captures[index - 1], captures[index]);
    }
  }
  return metres / 1000;
}

function sunAt(capture: Played) {
  return sunTimes(new Date(capture.capturedAt), capture);
}

function atDawn(capture: Played): boolean {
  const sun = sunAt(capture);
  const time = Date.parse(capture.capturedAt);
  return sun !== null && time >= sun.sunrise.getTime() && time <= sun.sunrise.getTime() + DAWN_MS;
}

function atNight(capture: Played): boolean {
  const sun = sunAt(capture);
  const time = Date.parse(capture.capturedAt);
  return sun !== null && (time < sun.sunrise.getTime() || time > sun.sunset.getTime());
}

function capturedIds(played: readonly Played[]): Set<string> {
  return new Set(played.map((capture) => capture.monumentId));
}

const isRare = (capture: Played) => capture.tier === 'rare' || capture.tier === 'légendaire';

/** Every badge, those of the series made from the series of the bundle. */
export function buildBadges(groups: Groups): Badge[] {
  const counts: [number, string, string, string, string][] = [
    [1, 'premiere-capture', 'Première capture', 'Capture ton premier monument.', '🎯'],
    [10, 'flaneur', 'Flâneur', 'Capture 10 monuments.', '🚶'],
    [25, 'arpenteur', 'Arpenteur', 'Capture 25 monuments.', '🧭'],
    [50, 'explorateur', 'Explorateur', 'Capture 50 monuments.', '🗺️'],
    [100, 'erudit', 'Érudit', 'Capture 100 monuments.', '📚'],
    [200, 'encyclopediste', 'Encyclopédiste', 'Capture 200 monuments.', '🏛️'],
  ];
  const series = groups.series.filter((one) => one.ids.length > 0);
  return [
    ...counts.map(([goal, slug, name, condition, icon]): Badge => ({
      slug,
      family: 'collection',
      name,
      condition,
      icon,
      measure: atLeast(goal, (played) => played.length),
    })),
    {
      slug: 'hors-des-sentiers',
      family: 'rarete',
      name: 'Hors des sentiers',
      condition: 'Capture un lieu rare ou légendaire.',
      icon: '🌿',
      measure: whether((played) => played.some(isRare)),
    },
    {
      slug: 'legende',
      family: 'rarete',
      name: 'Légende',
      condition: 'Capture un lieu légendaire.',
      icon: '✨',
      measure: whether((played) => played.some((capture) => capture.tier === 'légendaire')),
    },
    {
      slug: 'chasseur-de-legendes',
      family: 'rarete',
      name: 'Chasseur de légendes',
      condition: 'Capture 10 lieux légendaires.',
      icon: '👑',
      measure: atLeast(10, (played) => played.filter((capture) => capture.tier === 'légendaire').length),
    },
    {
      slug: 'deux-rives',
      family: 'paris',
      name: 'Les deux rives',
      condition: 'Capture un lieu sur la rive gauche et un sur la rive droite le même jour.',
      icon: '⛵',
      measure: whether((played) =>
        [...byDay(played).values()].some(
          (captures) =>
            captures.some(({ arrondissement }) => arrondissement !== null && LEFT_BANK.has(arrondissement)) &&
            captures.some(({ arrondissement }) => arrondissement !== null && !LEFT_BANK.has(arrondissement)),
        ),
      ),
    },
    {
      slug: 'tour-de-paris',
      family: 'paris',
      name: 'Tour de Paris',
      condition: 'Capture un lieu dans chacun des 20 arrondissements.',
      icon: '🗼',
      measure: atLeast(
        20,
        (played) =>
          new Set(played.flatMap(({ arrondissement }) => (arrondissement === null ? [] : [arrondissement]))).size,
      ),
    },
    {
      slug: 'quartier-conquis',
      family: 'paris',
      name: 'Quartier conquis',
      condition: 'Capture tous les lieux d’un arrondissement.',
      icon: '🚩',
      measure: whether((played) => {
        const captured = capturedIds(played);
        return groups.arrondissements.some(
          (group) => group.ids.length > 0 && group.ids.every((id) => captured.has(id)),
        );
      }),
    },
    {
      slug: 'collectionneur',
      family: 'series',
      name: 'Collectionneur',
      condition: 'Termine une série.',
      icon: '🏅',
      measure: whether((played) => {
        const captured = capturedIds(played);
        return series.some((one) => one.ids.every((id) => captured.has(id)));
      }),
    },
    ...series.map(
      (one): Badge => ({
        slug: `serie-${one.slug}`,
        family: 'series',
        name: one.name,
        condition: `Capture tous les lieux de la série « ${one.name} ».`,
        icon: SERIES_ICONS[one.slug] ?? '🏅',
        measure: atLeast(one.ids.length, (played) => {
          const captured = capturedIds(played);
          return one.ids.filter((id) => captured.has(id)).length;
        }),
      }),
    ),
    {
      slug: 'leve-tot',
      family: 'moments',
      name: 'Lève-tôt',
      condition: 'Capture un lieu dans l’heure qui suit le lever du soleil.',
      icon: '🌅',
      measure: whether((played) => played.some(atDawn)),
    },
    {
      slug: 'noctambule',
      family: 'moments',
      name: 'Noctambule',
      condition: 'Capture un lieu la nuit, entre le coucher et le lever du soleil.',
      icon: '🌙',
      measure: whether((played) => played.some(atNight)),
    },
    {
      slug: 'journee-chargee',
      family: 'moments',
      name: 'Journée chargée',
      condition: 'Capture 10 lieux le même jour.',
      icon: '📸',
      measure: atLeast(10, (played) =>
        Math.max(0, ...[...byDay(played).values()].map((captures) => captures.length)),
      ),
    },
    {
      slug: 'une-semaine-a-paris',
      family: 'moments',
      name: 'Une semaine à Paris',
      condition: 'Capture au moins un lieu 7 jours de suite.',
      icon: '📅',
      unit: 'jours',
      measure: atLeast(7, longestStreak),
    },
    {
      slug: 'quatre-saisons',
      family: 'moments',
      name: 'Quatre saisons',
      condition: 'Capture un lieu à chaque saison.',
      icon: '🍂',
      unit: 'saisons',
      measure: atLeast(4, (played) => new Set(played.map(({ capturedAt }) => seasonOf(parisDay(capturedAt)))).size),
    },
    ...([
      [10, 'bon-marcheur', 'Bon marcheur', '👟'],
      [42, 'marathonien', 'Marathonien', '🏃'],
    ] as const).map(
      ([goal, slug, name, icon]): Badge => ({
        slug,
        family: 'marche',
        name,
        condition: `Parcours ${goal} km d’une capture à l’autre : les trajets entre les captures d’une même journée s’additionnent, à vol d’oiseau.`,
        icon,
        unit: 'km',
        measure: atLeast(goal, (played) => Math.floor(walkedKm(played))),
      }),
    ),
  ];
}

/**
 * Where the player is with each badge, the captures given the oldest first.
 * The capture that won a badge is found by halving the captures, the measures
 * only growing with them.
 */
export function evaluate(badges: readonly Badge[], played: readonly Played[]): BadgeState[] {
  return badges.map((badge) => {
    const measure = badge.measure(played);
    if (measure.reached < measure.goal) {
      return { badge, measure, wonAt: null, wonWith: null };
    }
    let low = 1;
    let high = played.length;
    while (low < high) {
      const middle = Math.floor((low + high) / 2);
      const then = badge.measure(played.slice(0, middle));
      if (then.reached >= then.goal) {
        high = middle;
      } else {
        low = middle + 1;
      }
    }
    const winner = played[low - 1];
    return { badge, measure, wonAt: winner.capturedAt, wonWith: winner.monumentId };
  });
}
