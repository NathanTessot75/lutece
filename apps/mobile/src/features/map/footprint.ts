import type { LatLng } from 'react-native-maps';

/** One piece of an outline: its outer ring, and the courtyards cut out of it. */
export type Outline = {
  coordinates: LatLng[];
  holes: LatLng[][];
};

type MultiPolygon = {
  type: 'MultiPolygon';
  coordinates: [number, number][][][];
};

function toRing(positions: [number, number][]): LatLng[] {
  return positions.map(([longitude, latitude]) => ({ latitude, longitude }));
}

/** Read the outline of a monument from the GeoJSON multipolygon of the bundle. */
export function parseFootprint(geojson: string): Outline[] {
  const shape = JSON.parse(geojson) as MultiPolygon;
  return shape.coordinates.map(([outer, ...holes]) => ({
    coordinates: toRing(outer),
    holes: holes.map(toRing),
  }));
}
