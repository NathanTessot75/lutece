import { sunTimes } from './sun';
import { daysBetween, parisDay, parisOffsetMinutes, seasonOf } from './time';

const PARIS = { latitude: 48.8566, longitude: 2.3522 };

describe('Paris time', () => {
  it('changes its clocks on the last Sundays of March and October', () => {
    expect(parisOffsetMinutes(new Date('2026-03-29T00:59:00Z'))).toBe(60);
    expect(parisOffsetMinutes(new Date('2026-03-29T01:00:00Z'))).toBe(120);
    expect(parisOffsetMinutes(new Date('2026-10-25T00:59:00Z'))).toBe(120);
    expect(parisOffsetMinutes(new Date('2026-10-25T01:00:00Z'))).toBe(60);
  });

  it('gives the day in Paris, not in UTC', () => {
    expect(parisDay('2026-10-18T22:30:00Z')).toBe('2026-10-19');
    expect(parisDay('2026-12-01T22:30:00Z')).toBe('2026-12-01');
    expect(parisDay('2026-12-01T23:30:00Z')).toBe('2026-12-02');
  });

  it('counts the days between two days', () => {
    expect(daysBetween('2026-10-19', '2026-10-20')).toBe(1);
    // Across a change of clocks.
    expect(daysBetween('2026-10-24', '2026-10-26')).toBe(2);
    expect(daysBetween('2026-12-31', '2027-01-01')).toBe(1);
  });

  it('names the season of a day', () => {
    expect(seasonOf('2026-03-20')).toBe('printemps');
    expect(seasonOf('2026-06-21')).toBe('été');
    expect(seasonOf('2026-10-19')).toBe('automne');
    expect(seasonOf('2026-12-25')).toBe('hiver');
    expect(seasonOf('2027-02-01')).toBe('hiver');
  });
});

describe('sunTimes', () => {
  const minutesFrom = (date: Date, iso: string) =>
    Math.abs(date.getTime() - Date.parse(iso)) / 60_000;

  it('finds the sunrise and sunset of Paris within a few minutes', () => {
    // 5:47 and 21:58 in Paris at the summer solstice, 8:42 and 16:56 in winter.
    const summer = sunTimes(new Date('2026-06-21T12:00:00Z'), PARIS);
    expect(minutesFrom(summer!.sunrise, '2026-06-21T03:47:00Z')).toBeLessThan(4);
    expect(minutesFrom(summer!.sunset, '2026-06-21T19:58:00Z')).toBeLessThan(4);
    const winter = sunTimes(new Date('2026-12-21T12:00:00Z'), PARIS);
    expect(minutesFrom(winter!.sunrise, '2026-12-21T07:42:00Z')).toBeLessThan(4);
    expect(minutesFrom(winter!.sunset, '2026-12-21T15:56:00Z')).toBeLessThan(4);
  });

  it('gives nothing where the sun does not set', () => {
    expect(sunTimes(new Date('2026-06-21T12:00:00Z'), { latitude: 80, longitude: 0 })).toBeNull();
  });
});
