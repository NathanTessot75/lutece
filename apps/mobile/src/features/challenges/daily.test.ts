import { drawDailyPlace, fnv1a32, formatTimeLeft, today, untilMidnight } from './daily';

// The seed and the places of supabase/tests/database/daily_challenge.test.sql:
// the app must draw the places that the server draws.
const SEED = '0123456789abcdef0123456789abcdef';
const PLACES = [1, 2, 3, 4].map((n) => ({
  id: `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`,
  readiness: 'ready',
}));
const place = (n: number) => PLACES[n - 1];
const none = new Set<string>();

describe('fnv1a32', () => {
  it('gives the fingerprints of FNV-1a, over UTF-8', () => {
    expect(fnv1a32('')).toBe(2166136261);
    expect(fnv1a32('foobar')).toBe(3214735720);
    expect(fnv1a32('é')).toBe(513665217);
  });
});

describe('drawDailyPlace', () => {
  it('draws the places that the server draws', () => {
    expect(drawDailyPlace(SEED, '2026-11-10', PLACES, none)).toBe(place(4));
    expect(drawDailyPlace(SEED, '2026-11-11', PLACES, none)).toBe(place(3));
  });

  it('never draws a place that cannot be captured', () => {
    const notReady = PLACES.map((one) => (one === place(4) ? { ...one, readiness: 'not_ready' } : one));
    expect(drawDailyPlace(SEED, '2026-11-10', notReady, none)?.id).toBe(place(1).id);
  });

  it('leaves out the places captured before the day', () => {
    const captured = new Set([place(4).id, place(1).id]);
    expect(drawDailyPlace(SEED, '2026-11-15', PLACES, captured)).toBe(place(3));
    expect(drawDailyPlace(SEED, '2026-11-16', PLACES, captured)).toBe(place(2));
  });

  it('draws nothing once every place is captured', () => {
    expect(drawDailyPlace(SEED, '2026-11-10', PLACES, new Set(PLACES.map((one) => one.id)))).toBeNull();
  });
});

describe('the day in Paris', () => {
  it('turns at midnight in Paris, not in UTC', () => {
    expect(today(new Date('2026-11-17T22:59:00Z'))).toBe('2026-11-17');
    expect(today(new Date('2026-11-17T23:00:00Z'))).toBe('2026-11-18');
    expect(today(new Date('2026-07-01T22:30:00Z'))).toBe('2026-07-02');
  });

  it('counts the time left until midnight in Paris', () => {
    expect(untilMidnight(new Date('2026-11-17T16:18:00Z'))).toBe((6 * 60 + 42) * 60_000);
    expect(untilMidnight(new Date('2026-11-17T23:00:00Z'))).toBe(24 * 60 * 60_000);
    expect(formatTimeLeft((7 * 60 + 42) * 60_000)).toBe('7 h 42');
    expect(formatTimeLeft(18 * 60_000)).toBe('18 min');
    expect(formatTimeLeft((3 * 60 + 5) * 60_000)).toBe('3 h 05');
  });
});
