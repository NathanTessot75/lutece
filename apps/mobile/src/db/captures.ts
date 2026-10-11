import type { SQLiteDatabase } from 'expo-sqlite';

/** What is known when a monument is captured (SPEC §5.3). */
export type NewCapture = {
  monumentId: string;
  latitude: number;
  longitude: number;
  gpsAccuracyM: number;
  /** Where the phone pointed, when the compass could tell. */
  headingDeg: number | null;
  /** How well the compass was calibrated, from 0 to 3: iOS gives no degrees. */
  headingLevel: number | null;
  geoScore: number;
  /** Whether the player picked the monument among several candidates. */
  chosenByPlayer: boolean;
  /** The name of the picture, in the folder of the captures. */
  photoFile: string | null;
};

// A random identifier (UUID version 4), written by SQLite itself.
const NEW_ID = `
  lower(
    hex(randomblob(4)) || '-' || hex(randomblob(2)) || '-4' ||
    substr(hex(randomblob(2)), 2) || '-' ||
    substr('89ab', abs(random()) % 4 + 1, 1) || substr(hex(randomblob(2)), 2) || '-' ||
    hex(randomblob(6))
  )
`;

// Without image recognition, the final score is the one of the geometry.
// A monument is captured once: a second capture changes nothing.
const INSERT = `
  insert or ignore into captures (
    id, monument_id, captured_at, lat, lon, gps_accuracy_m, heading_deg,
    heading_level, geo_score, final_score, status, chosen_by_player, photo_file
  ) values (
    ${NEW_ID}, $monumentId, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), $lat, $lon,
    $gpsAccuracyM, $headingDeg, $headingLevel, $geoScore, $geoScore, 'accepted',
    $chosenByPlayer, $photoFile
  )
`;

export async function saveCapture(db: SQLiteDatabase, capture: NewCapture): Promise<void> {
  await db.runAsync(INSERT, {
    $monumentId: capture.monumentId,
    $lat: capture.latitude,
    $lon: capture.longitude,
    $gpsAccuracyM: capture.gpsAccuracyM,
    $headingDeg: capture.headingDeg,
    $headingLevel: capture.headingLevel,
    $geoScore: capture.geoScore,
    $chosenByPlayer: capture.chosenByPlayer ? 1 : 0,
    $photoFile: capture.photoFile,
  });
}

/** The monuments that the player has already captured. */
export async function listCapturedIds(db: SQLiteDatabase): Promise<Set<string>> {
  const rows = await db.getAllAsync<{ monument_id: string }>('select monument_id from captures');
  return new Set(rows.map((row) => row.monument_id));
}
