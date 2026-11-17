import { parisDay, parisOffsetMinutes } from '@/features/game/time';

/** The capture of the place of the day is worth this many times its points. */
export const DAILY_MULTIPLIER = 3;

const MINUTE_MS = 60_000;
const DAY_MS = 86_400_000;

/**
 * FNV-1a on 32 bits, over the bytes of the text in UTF-8: the fingerprint
 * that the server computes too (supabase/migrations/*_daily_challenge.sql).
 */
export function fnv1a32(text: string): number {
  let hash = 2166136261;
  for (const byte of new TextEncoder().encode(text)) {
    hash ^= byte;
    hash = Math.imul(hash, 16777619) >>> 0;
  }
  return hash >>> 0;
}

type Place = { id: string; readiness: string };

/**
 * The place of the day of a player: among the places they can capture and
 * had not captured before that day, the one whose fingerprint of the seed, the
 * day and the place is the smallest. The server draws the same, to triple the
 * points of its capture. None once every place is captured.
 */
export function drawDailyPlace<T extends Place>(
  seed: string,
  day: string,
  places: readonly T[],
  capturedBefore: { has: (id: string) => boolean },
): T | null {
  let best: { place: T; print: number } | null = null;
  for (const place of places) {
    if (place.readiness === 'not_ready' || capturedBefore.has(place.id)) {
      continue;
    }
    const print = fnv1a32(`${seed}:${day}:${place.id}`);
    if (best === null || print < best.print || (print === best.print && place.id < best.place.id)) {
      best = { place, print };
    }
  }
  return best?.place ?? null;
}

/** The day in Paris at a moment: « 2026-11-18 ». */
export function today(now: Date): string {
  return parisDay(now.toISOString());
}

/** How long until midnight in Paris, when the place of the day changes. */
export function untilMidnight(now: Date): number {
  const offset = parisOffsetMinutes(now) * MINUTE_MS;
  const inParis = now.getTime() + offset;
  return Math.ceil(inParis / DAY_MS) * DAY_MS - inParis || DAY_MS;
}

/** 27_720_000 → « 7 h 42 »; under an hour, « 18 min ». */
export function formatTimeLeft(ms: number): string {
  const minutes = Math.ceil(ms / MINUTE_MS);
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours === 0) {
    return `${rest} min`;
  }
  return `${hours} h ${String(rest).padStart(2, '0')}`;
}
