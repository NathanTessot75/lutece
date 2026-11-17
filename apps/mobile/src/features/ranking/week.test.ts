import { formatWeekLeft, untilNextWeek } from './week';

const HOUR_MS = 3_600_000;
const DAY_MS = 86_400_000;

describe('untilNextWeek', () => {
  it('counts the time left until Monday midnight in Paris', () => {
    // Wednesday 18 November at 0:30 in Paris.
    expect(untilNextWeek(new Date('2026-11-17T23:30:00Z'))).toBe(4 * DAY_MS + 23.5 * HOUR_MS);
    // Sunday 22 November at 23:30 in Paris.
    expect(untilNextWeek(new Date('2026-11-22T22:30:00Z'))).toBe(0.5 * HOUR_MS);
  });

  it('gives a whole week at Monday midnight', () => {
    expect(untilNextWeek(new Date('2026-11-15T23:00:00Z'))).toBe(7 * DAY_MS);
  });

  it('follows the change of the clocks before Monday', () => {
    // Tuesday 24 March at noon in winter time; Monday 30 March starts in summer time.
    expect(untilNextWeek(new Date('2026-03-24T11:00:00Z'))).toBe(5 * DAY_MS + 11 * HOUR_MS);
    // Tuesday 20 October at noon in summer time; Monday 26 October starts in winter time.
    expect(untilNextWeek(new Date('2026-10-20T10:00:00Z'))).toBe(5 * DAY_MS + 13 * HOUR_MS);
  });
});

describe('formatWeekLeft', () => {
  it('writes days and hours, then the time of the last day', () => {
    expect(formatWeekLeft(5 * DAY_MS + 23.5 * HOUR_MS)).toBe('5 j 23 h');
    expect(formatWeekLeft(2 * DAY_MS)).toBe('2 j');
    expect(formatWeekLeft(7 * HOUR_MS + 42 * 60_000)).toBe('7 h 42');
  });
});
