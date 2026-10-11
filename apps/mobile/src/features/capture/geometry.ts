import type { Outline } from '@/features/map/footprint';

/** A place on the ground, in degrees. */
export type Coordinates = {
  latitude: number;
  longitude: number;
};

/** How a monument stands from where the player is. */
export type Sighting = {
  /** Metres to the nearest point of the outline; 0 when standing inside it. */
  distanceM: number;
  /** Direction of that point, in degrees clockwise from north; none when inside. */
  bearingDeg: number | null;
};

type Point = { x: number; y: number };

const EARTH_RADIUS_M = 6_371_008.8;

function toRadians(degrees: number): number {
  return (degrees * Math.PI) / 180;
}

/**
 * Metres east and north of an origin. Over the few hundred metres of a
 * capture, the ground is flat enough for this to be right within centimetres.
 */
function toPlane(origin: Coordinates, place: Coordinates): Point {
  return {
    x:
      toRadians(place.longitude - origin.longitude) *
      Math.cos(toRadians(origin.latitude)) *
      EARTH_RADIUS_M,
    y: toRadians(place.latitude - origin.latitude) * EARTH_RADIUS_M,
  };
}

/** Metres between two places close to each other. */
export function distanceBetween(first: Coordinates, second: Coordinates): number {
  const { x, y } = toPlane(first, second);
  return Math.hypot(x, y);
}

/** Whether the origin lies inside a ring, by counting the edges east of it. */
function surroundsOrigin(ring: Point[]): boolean {
  let inside = false;
  for (let index = 0, previous = ring.length - 1; index < ring.length; previous = index++) {
    const start = ring[previous];
    const end = ring[index];
    const crossesAxis = start.y > 0 !== end.y > 0;
    if (crossesAxis && start.x + ((0 - start.y) * (end.x - start.x)) / (end.y - start.y) > 0) {
      inside = !inside;
    }
  }
  return inside;
}

/** The point of a segment that is nearest to the origin. */
function nearestOnSegment(start: Point, end: Point): Point {
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const length2 = dx * dx + dy * dy;
  const along = length2 === 0 ? 0 : Math.min(1, Math.max(0, -(start.x * dx + start.y * dy) / length2));
  return { x: start.x + along * dx, y: start.y + along * dy };
}

function nearestOnRing(ring: Point[]): Point | null {
  let nearest: Point | null = null;
  for (let index = 0; index + 1 < ring.length; index++) {
    const candidate = nearestOnSegment(ring[index], ring[index + 1]);
    if (nearest === null || Math.hypot(candidate.x, candidate.y) < Math.hypot(nearest.x, nearest.y)) {
      nearest = candidate;
    }
  }
  return nearest;
}

/** How far the outline of a monument is from a place, and in which direction. */
export function sight(from: Coordinates, outlines: Outline[]): Sighting {
  let nearest: Point | null = null;
  for (const outline of outlines) {
    const outer = outline.coordinates.map((corner) => toPlane(from, corner));
    const holes = outline.holes.map((hole) => hole.map((corner) => toPlane(from, corner)));
    // Standing in a courtyard cut out of the outline is standing outside it.
    if (surroundsOrigin(outer) && !holes.some(surroundsOrigin)) {
      return { distanceM: 0, bearingDeg: null };
    }
    for (const ring of [outer, ...holes]) {
      const candidate = nearestOnRing(ring);
      if (
        candidate !== null &&
        (nearest === null || Math.hypot(candidate.x, candidate.y) < Math.hypot(nearest.x, nearest.y))
      ) {
        nearest = candidate;
      }
    }
  }
  if (nearest === null) {
    return { distanceM: Infinity, bearingDeg: null };
  }
  const bearing = (Math.atan2(nearest.x, nearest.y) * 180) / Math.PI;
  return { distanceM: Math.hypot(nearest.x, nearest.y), bearingDeg: (bearing + 360) % 360 };
}

/** How far to turn from one direction to another: negative to the left, up to 180°. */
export function turn(fromDeg: number, toDeg: number): number {
  return ((((toDeg - fromDeg) % 360) + 540) % 360) - 180;
}
