import type { SQLiteDatabase } from 'expo-sqlite';
import type { Region } from 'react-native-maps';

import { type MonumentPlace, listCells, listPlaces } from '@/db/monuments';

import { boundsOf, cellsOf, gridFor } from './grid';

/** What the map draws: one monument, or several gathered where it is crowded. */
export type Mark =
  | { kind: 'monument'; monument: MonumentPlace }
  | { kind: 'group'; key: string; count: number; latitude: number; longitude: number };

/** The marks of a region: every monument when zoomed in, groups otherwise. */
export async function loadMarks(db: SQLiteDatabase, region: Region): Promise<Mark[]> {
  const bounds = boundsOf(region);
  const grid = gridFor(region);
  if (grid === null) {
    const places = await listPlaces(db, bounds);
    return places.map((monument) => ({ kind: 'monument', monument }));
  }
  const cells = await listCells(db, grid, cellsOf(bounds, grid));
  return cells.map((cell) =>
    cell.monument
      ? { kind: 'monument', monument: cell.monument }
      : {
          kind: 'group',
          key: `${grid.latStep}:${cell.row}:${cell.column}`,
          count: cell.count,
          latitude: cell.lat,
          longitude: cell.lon,
        },
  );
}
