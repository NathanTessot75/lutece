const MINUTE_MS = 60_000;
const DAY_MS = 86_400_000;

/** The last Sunday of a month at 1:00 UTC, when Paris changes its clocks. */
function lastSundayAtOne(year: number, month: number): number {
  const last = new Date(Date.UTC(year, month + 1, 0, 1));
  last.setUTCDate(last.getUTCDate() - last.getUTCDay());
  return last.getTime();
}

/** How far Paris is ahead of UTC at a moment: 2 hours in summer, 1 in winter. */
export function parisOffsetMinutes(at: Date): number {
  const year = at.getUTCFullYear();
  const time = at.getTime();
  return time >= lastSundayAtOne(year, 2) && time < lastSundayAtOne(year, 9) ? 120 : 60;
}

/** The day in Paris of a moment written in UTC: « 2026-10-19 ». */
export function parisDay(iso: string): string {
  const at = new Date(iso);
  return new Date(at.getTime() + parisOffsetMinutes(at) * MINUTE_MS).toISOString().slice(0, 10);
}

/** How many days from one Paris day to another. */
export function daysBetween(first: string, second: string): number {
  return Math.round((Date.parse(second) - Date.parse(first)) / DAY_MS);
}

export type Season = 'printemps' | 'été' | 'automne' | 'hiver';

/** The season of a day, on the usual dates of the equinoxes and solstices. */
export function seasonOf(day: string): Season {
  const monthDay = day.slice(5);
  if (monthDay >= '03-20' && monthDay < '06-21') {
    return 'printemps';
  }
  if (monthDay >= '06-21' && monthDay < '09-22') {
    return 'été';
  }
  if (monthDay >= '09-22' && monthDay < '12-21') {
    return 'automne';
  }
  return 'hiver';
}
