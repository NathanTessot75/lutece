import { formatTimeLeft } from '@/features/challenges/daily';
import { parisOffsetMinutes } from '@/features/game/time';

const MINUTE_MS = 60_000;
const HOUR_MS = 3_600_000;
const DAY_MS = 86_400_000;

/**
 * How long until Monday midnight in Paris, when the leaderboard of the week
 * starts again (public.week_start on the server).
 */
export function untilNextWeek(now: Date): number {
  const inParis = now.getTime() + parisOffsetMinutes(now) * MINUTE_MS;
  const day = Math.floor(inParis / DAY_MS);
  const sinceMonday = (new Date(day * DAY_MS).getUTCDay() + 6) % 7;
  const monday = (day + 7 - sinceMonday) * DAY_MS;
  // The clocks may change before Monday: its offset is that of Monday.
  const guess = monday - parisOffsetMinutes(now) * MINUTE_MS;
  return monday - parisOffsetMinutes(new Date(guess)) * MINUTE_MS - now.getTime();
}

/** « 5 j 23 h », « 2 j »; under a day, as the time left of the day: « 7 h 42 ». */
export function formatWeekLeft(ms: number): string {
  if (ms < DAY_MS) {
    return formatTimeLeft(ms);
  }
  const days = Math.floor(ms / DAY_MS);
  const hours = Math.floor((ms % DAY_MS) / HOUR_MS);
  return hours === 0 ? `${days} j` : `${days} j ${hours} h`;
}
