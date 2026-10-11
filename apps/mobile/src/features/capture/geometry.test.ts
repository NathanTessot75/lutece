import { sight, turn } from './geometry';
import { HERE, at, block } from './testing';

describe('sight', () => {
  it('measures the distance and the direction to the nearest wall', () => {
    // A building 40 m to the north, 20 m wide and 30 m deep.
    const north = sight(HERE, [block(-10, 40, 10, 70)]);
    expect(north.distanceM).toBeCloseTo(40, 1);
    expect(north.bearingDeg).toBeCloseTo(0, 1);

    const east = sight(HERE, [block(25, -5, 60, 5)]);
    expect(east.distanceM).toBeCloseTo(25, 1);
    expect(east.bearingDeg).toBeCloseTo(90, 1);
  });

  it('aims at the nearest corner of a building that is aside', () => {
    // Its nearest corner is 30 m east and 40 m south: 50 m away, to the south-east.
    const aside = sight(HERE, [block(30, -80, 90, -40)]);
    expect(aside.distanceM).toBeCloseTo(50, 1);
    expect(aside.bearingDeg).toBeCloseTo(180 - (Math.atan2(30, 40) * 180) / Math.PI, 1);
  });

  it('is at no distance from an outline it stands in', () => {
    expect(sight(HERE, [block(-50, -50, 50, 50)])).toEqual({ distanceM: 0, bearingDeg: null });
  });

  it('stands outside the outline when in its courtyard', () => {
    const palace = block(-50, -50, 50, 50);
    palace.holes = [block(-20, -10, 30, 10).coordinates];
    const fromCourtyard = sight(HERE, [palace]);
    // The wall of the courtyard is nearest 10 m away, north as well as south.
    expect(fromCourtyard.distanceM).toBeCloseTo(10, 1);
    expect([0, 180]).toContain(Math.round(fromCourtyard.bearingDeg ?? -1));
  });

  it('takes the nearest piece of an outline in several pieces', () => {
    const pieces = [block(-10, 200, 10, 220), block(-70, -5, -60, 5)];
    const nearest = sight(HERE, pieces);
    expect(nearest.distanceM).toBeCloseTo(60, 1);
    expect(nearest.bearingDeg).toBeCloseTo(270, 1);
  });

  it('measures the same from another place', () => {
    const from = at(0, -100);
    expect(sight(from, [block(-10, 40, 10, 70)]).distanceM).toBeCloseTo(140, 1);
  });

  it('sees nothing of a monument without outline', () => {
    expect(sight(HERE, [])).toEqual({ distanceM: Infinity, bearingDeg: null });
  });
});

describe('turn', () => {
  it.each([
    [0, 30, 30],
    [30, 0, -30],
    [350, 10, 20],
    [10, 350, -20],
    [90, 270, -180],
    [0, 179, 179],
    [0, 181, -179],
    [720, 45, 45],
  ])('from %d° to %d° is %d°', (from, to, expected) => {
    expect(turn(from, to)).toBeCloseTo(expected, 6);
  });
});
