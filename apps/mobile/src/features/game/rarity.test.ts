import { formatPoints, pointsFor, tierLabel, tierNote, totalPoints } from './rarity';

describe('pointsFor', () => {
  it('rewards the places that few people know', () => {
    expect(pointsFor('commun')).toBe(10);
    expect(pointsFor('peu_commun')).toBe(25);
    expect(pointsFor('rare')).toBe(50);
    expect(pointsFor('légendaire')).toBe(100);
  });

  it('counts a place without a tier as common', () => {
    expect(pointsFor(null)).toBe(10);
  });
});

describe('labels', () => {
  it('names the tiers in French', () => {
    expect(tierLabel('peu_commun')).toBe('Peu commun');
    expect(tierLabel('légendaire')).toBe('Légendaire');
  });

  it('explains only the rare tiers', () => {
    expect(tierNote('commun')).toBeNull();
    expect(tierNote(null)).toBeNull();
    expect(tierNote('légendaire')).toMatch(/moins connus/);
  });

  it('writes points as a count', () => {
    expect(formatPoints(1)).toBe('1 point');
    expect(formatPoints(0)).toBe('0 point');
    expect(formatPoints(1250)).toBe('1 250 points');
  });
});

describe('totalPoints', () => {
  it('adds the points of the captures', () => {
    expect(totalPoints([{ points: 10 }, { points: 100 }, { points: null }])).toBe(110);
    expect(totalPoints([])).toBe(0);
  });
});
