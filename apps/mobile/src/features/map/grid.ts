import type { Region } from 'react-native-maps';

import type { Bounds, CellRange, Grid } from '@/db/monuments';

/** Paris as a whole, where the map opens. */
export const PARIS: Region = {
  latitude: 48.8589,
  longitude: 2.3469,
  latitudeDelta: 0.09,
  longitudeDelta: 0.21,
};

/** What the map shows around a person: a few streets. */
export const NEIGHBOURHOOD_SPAN = 0.008;

/** Where the monuments of the bundle are, with some room around. */
const PARIS_BOUNDS: Bounds = { south: 48.8, north: 48.92, west: 2.2, east: 2.5 };

// Below this height of map, about 550 m, every monument gets its own pin.
const DETAIL_SPAN = 0.005;
// How many squares fit in the height of the map, at least; at most twice as
// many, which still leaves each group more room than its mark takes.
const ROWS = 6;
// The smallest square, about 50 m; the others are 2, 4, 8... times larger, so
// that the groups stay the same while the map zooms a little.
const SMALLEST_STEP = 0.00045;
// At the latitude of Paris, a degree of longitude is 1.5 times shorter than a
// degree of latitude: the squares are that much wider in degrees.
const LON_PER_LAT = 1.5;
// What is fetched beyond each edge of the map, as a share of its size, so
// that a small move does not uncover an empty strip.
const MARGIN = 0.25;

/** The grid that groups the monuments at this zoom, or none when all are shown. */
export function gridFor(region: Region): Grid | null {
  if (region.latitudeDelta <= DETAIL_SPAN) {
    return null;
  }
  const wanted = region.latitudeDelta / ROWS / 2;
  const doublings = Math.max(0, Math.ceil(Math.log2(wanted / SMALLEST_STEP)));
  const latStep = SMALLEST_STEP * 2 ** doublings;
  return { latStep, lonStep: latStep * LON_PER_LAT };
}

/** What the map shows, with a margin around. */
export function boundsOf(region: Region): Bounds {
  const halfHeight = region.latitudeDelta * (0.5 + MARGIN);
  const halfWidth = region.longitudeDelta * (0.5 + MARGIN);
  return {
    south: region.latitude - halfHeight,
    north: region.latitude + halfHeight,
    west: region.longitude - halfWidth,
    east: region.longitude + halfWidth,
  };
}

/** The squares of the grid that the bounds touch. */
export function cellsOf(bounds: Bounds, grid: Grid): CellRange {
  return {
    firstRow: Math.floor(bounds.south / grid.latStep),
    lastRow: Math.floor(bounds.north / grid.latStep),
    firstColumn: Math.floor(bounds.west / grid.lonStep),
    lastColumn: Math.floor(bounds.east / grid.lonStep),
  };
}

export function isInParis(latitude: number, longitude: number): boolean {
  return (
    latitude >= PARIS_BOUNDS.south &&
    latitude <= PARIS_BOUNDS.north &&
    longitude >= PARIS_BOUNDS.west &&
    longitude <= PARIS_BOUNDS.east
  );
}
