import type { SQLiteDatabase } from 'expo-sqlite';

/** A sample of the collect mode not sent yet, as the player database keeps it. */
export type UnsentSample = {
  id: string;
  takenAt: string;
  lat: number;
  lon: number;
  gpsAccuracyM: number;
  headingDeg: number | null;
  headingLevel: number | null;
  photoFile: string | null;
  vector: Uint8Array | null;
  candidates: string;
  decision: string;
  labelMonumentId: string | null;
  oblique: number;
  hidden: number;
  bundleVersion: string;
  model: string;
  appVersion: string;
};

/** A capture not sent yet. */
export type UnsentCapture = {
  id: string;
  monumentId: string;
  capturedAt: string;
  lat: number;
  lon: number;
  gpsAccuracyM: number;
  headingDeg: number | null;
  headingLevel: number | null;
  geoScore: number;
  imageScore: number | null;
  chosenByPlayer: number;
  photoFile: string | null;
};

export async function listUnsentSamples(db: SQLiteDatabase): Promise<UnsentSample[]> {
  return db.getAllAsync<UnsentSample>(`
    select id, taken_at as takenAt, lat, lon, gps_accuracy_m as gpsAccuracyM,
      heading_deg as headingDeg, heading_level as headingLevel,
      photo_file as photoFile, vector, candidates, decision,
      label_monument_id as labelMonumentId, oblique, hidden,
      bundle_version as bundleVersion, model, app_version as appVersion
    from samples where uploaded_at is null order by taken_at
  `);
}

export async function listUnsentCaptures(db: SQLiteDatabase): Promise<UnsentCapture[]> {
  return db.getAllAsync<UnsentCapture>(`
    select id, monument_id as monumentId, captured_at as capturedAt, lat, lon,
      gps_accuracy_m as gpsAccuracyM, heading_deg as headingDeg,
      heading_level as headingLevel, geo_score as geoScore,
      image_score as imageScore, chosen_by_player as chosenByPlayer,
      photo_file as photoFile
    from captures where uploaded_at is null order by captured_at
  `);
}

/** Write down that a sample or a capture reached the server. */
export async function markSent(
  db: SQLiteDatabase,
  table: 'samples' | 'captures',
  id: string,
): Promise<void> {
  await db.runAsync(
    `update ${table} set uploaded_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') where id = $id`,
    { $id: id },
  );
}

/** Forget what was sent, once the player has deleted it from the server. */
export async function forgetSent(db: SQLiteDatabase): Promise<void> {
  await db.execAsync('update samples set uploaded_at = null; update captures set uploaded_at = null;');
}

/** How many photos were sent, and how many wait. */
export async function countSent(db: SQLiteDatabase): Promise<{ sent: number; waiting: number }> {
  const row = await db.getFirstAsync<{ sent: number; waiting: number }>(`
    select
      (select count(*) from samples where uploaded_at is not null)
        + (select count(*) from captures where uploaded_at is not null) as sent,
      (select count(*) from samples where uploaded_at is null)
        + (select count(*) from captures where uploaded_at is null) as waiting
  `);
  return row ?? { sent: 0, waiting: 0 };
}
