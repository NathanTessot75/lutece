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
  /** How much the photo looks like the monument; none without a photo or a reference photo. */
  imageScore: number | null;
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

// The geometry chooses the candidates and the photo tells them apart: the
// final score is the likeness of the photo, or the score of the geometry when
// the photo could not tell. Phase 4 will learn how to weigh the two.
// A monument is captured once: a second capture changes nothing.
const INSERT = `
  insert or ignore into captures (
    id, monument_id, captured_at, lat, lon, gps_accuracy_m, heading_deg,
    heading_level, geo_score, image_score, final_score, status, chosen_by_player,
    photo_file
  ) values (
    ${NEW_ID}, $monumentId, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), $lat, $lon,
    $gpsAccuracyM, $headingDeg, $headingLevel, $geoScore, $imageScore,
    coalesce($imageScore, $geoScore), 'accepted', $chosenByPlayer, $photoFile
  )
`;

/** A capture as the collection shows it. */
export type Capture = {
  monumentId: string;
  /** When it was made, as an ISO 8601 date in UTC. */
  capturedAt: string;
  photoFile: string | null;
};

const CAPTURES = `
  select monument_id as monumentId, captured_at as capturedAt, photo_file as photoFile
  from captures
  order by captured_at desc
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
    $imageScore: capture.imageScore,
    $chosenByPlayer: capture.chosenByPlayer ? 1 : 0,
    $photoFile: capture.photoFile,
  });
}

/** What the player has captured, the latest first. */
export async function listCaptures(db: SQLiteDatabase): Promise<Capture[]> {
  return db.getAllAsync<Capture>(CAPTURES);
}
