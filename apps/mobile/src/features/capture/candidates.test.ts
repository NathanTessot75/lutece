import {
  type Compass,
  type Fix,
  type Target,
  allowedDistance,
  coneHalfWidth,
  findCandidates,
} from './candidates';
import { HERE, block } from './testing';

const PRECISE: Fix = { ...HERE, accuracyM: 5 };
const NORTH: Compass = { headingDeg: 0, level: 3 };

function target(id: string, outline: ReturnType<typeof block>, reachM = 0): Target {
  return { id, reachM, outlines: [outline] };
}

function ids(fix: Fix, compass: Compass | null, targets: Target[], inSight = true): string[] {
  return findCandidates(fix, compass, targets)
    .filter((candidate) => candidate.inSight === inSight)
    .map((candidate) => candidate.target.id);
}

describe('allowedDistance', () => {
  it.each([
    // [accuracy of the GPS, reach of the monument, distance allowed]
    [5, 0, 50],
    [40, 0, 80],
    [100, 0, 150],
    [5, 272, 272],
    [100, 60, 150],
    [100, 800, 800],
  ])('with a fix within %d m and a reach of %d m, allows %d m', (accuracy, reach, expected) => {
    expect(allowedDistance(accuracy, reach)).toBe(expected);
  });
});

describe('coneHalfWidth', () => {
  it('widens as the compass gets worse, and gives up when it is lost', () => {
    expect(coneHalfWidth(3)).toBe(50);
    expect(coneHalfWidth(2)).toBe(65);
    expect(coneHalfWidth(1)).toBe(80);
    expect(coneHalfWidth(0)).toBeNull();
    expect(coneHalfWidth(-1)).toBeNull();
  });
});

describe('findCandidates', () => {
  const church = target('church', block(-10, 30, 10, 60));
  const shop = target('shop', block(-45, -5, -35, 5));
  const tower = target('tower', block(-10, 400, 10, 420), 800);
  const theatre = target('theatre', block(-10, 200, 10, 230));

  it('keeps what is within reach and faced, the best one first', () => {
    const found = findCandidates(PRECISE, NORTH, [shop, tower, theatre, church]);
    expect(found.map((candidate) => candidate.target.id)).toEqual(['church', 'tower', 'shop']);
    expect(found.map((candidate) => candidate.inSight)).toEqual([true, true, false]);
    // The theatre is 200 m away: too far for its size.
    expect(found[0].distanceM).toBeCloseTo(30, 1);
    expect(found[0].offsetDeg).toBeCloseTo(0, 1);
    // Straight ahead: all of the half for the direction, and 50 / (50 + 30) of
    // the half for the distance.
    expect(found[0].score).toBeCloseTo(0.5 * (50 / 80) + 0.5, 2);
    // The tower is as well faced, but 400 m away.
    expect(found[1].score).toBeCloseTo(0.5 * (50 / 450) + 0.5, 2);
    // The shop is 35 m to the west: a quarter turn to the left.
    expect(found[2].offsetDeg).toBeCloseTo(-90, 1);
    expect(found[2].score).toBe(0);
  });

  it('follows the phone as it turns', () => {
    const west: Compass = { headingDeg: 270, level: 3 };
    expect(ids(PRECISE, west, [church, shop])).toEqual(['shop']);
    const northWest: Compass = { headingDeg: 315, level: 3 };
    // Both are 45° away, within the 50° of a good compass.
    expect(ids(PRECISE, northWest, [church, shop])).toEqual(['church', 'shop']);
    const south: Compass = { headingDeg: 180, level: 3 };
    expect(ids(PRECISE, south, [church, shop])).toEqual([]);
  });

  it('looks wider with a poor compass', () => {
    const northEast: Compass = { headingDeg: 60, level: 3 };
    expect(ids(PRECISE, northEast, [church])).toEqual([]);
    expect(ids(PRECISE, { ...northEast, level: 2 }, [church])).toEqual(['church']);
  });

  it('reaches further with a poor fix, as the SPEC allows', () => {
    const cinema = target('cinema', block(-10, 100, 10, 130));
    expect(ids(PRECISE, NORTH, [cinema])).toEqual([]);
    expect(ids({ ...HERE, accuracyM: 60 }, NORTH, [cinema])).toEqual(['cinema']);
  });

  it('faces nothing without a compass, but still tells what is around', () => {
    for (const lost of [null, { headingDeg: 0, level: 0 }]) {
      expect(ids(PRECISE, lost, [church, shop])).toEqual([]);
      expect(ids(PRECISE, lost, [church, shop], false)).toEqual(['church', 'shop']);
    }
    expect(findCandidates(PRECISE, null, [church])[0].offsetDeg).toBeNull();
  });

  it('faces the monument the player stands in, whatever the compass', () => {
    const garden = target('garden', block(-100, -100, 100, 100));
    const [inside] = findCandidates(PRECISE, null, [garden]);
    expect(inside).toMatchObject({ distanceM: 0, offsetDeg: 0, inSight: true, score: 1 });
    // It comes before a building that is faced from outside.
    expect(ids(PRECISE, NORTH, [church, garden])).toEqual(['garden', 'church']);
  });

  it('prefers the nearer of two monuments in the same direction', () => {
    const behind = target('behind', block(-10, 35, 10, 45));
    const front = target('front', block(-10, 10, 10, 20));
    expect(ids(PRECISE, NORTH, [behind, front])).toEqual(['front', 'behind']);
  });

  it('prefers the better faced of two monuments at the same distance', () => {
    const ahead = target('ahead', block(-5, 30, 5, 40));
    const aside = target('aside', block(20, 22, 30, 32));
    expect(ids(PRECISE, NORTH, [aside, ahead])).toEqual(['ahead', 'aside']);
  });
});
