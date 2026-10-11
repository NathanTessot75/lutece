import type { Outline } from '@/features/map/footprint';

import type { Coordinates } from './geometry';

/** In front of Notre-Dame: where the tests stand. */
export const HERE: Coordinates = { latitude: 48.8534, longitude: 2.3488 };

const METRES_PER_DEGREE = 111_195;

/** The place that many metres east and north of where the tests stand. */
export function at(eastM: number, northM: number): Coordinates {
  return {
    latitude: HERE.latitude + northM / METRES_PER_DEGREE,
    longitude:
      HERE.longitude +
      eastM / (METRES_PER_DEGREE * Math.cos((HERE.latitude * Math.PI) / 180)),
  };
}

/** A rectangular outline, given by two opposite corners in metres. */
export function block(west: number, south: number, east: number, north: number): Outline {
  return {
    coordinates: [
      at(west, south),
      at(east, south),
      at(east, north),
      at(west, north),
      at(west, south),
    ],
    holes: [],
  };
}
