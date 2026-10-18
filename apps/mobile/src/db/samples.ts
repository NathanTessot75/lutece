import type { SQLiteDatabase } from 'expo-sqlite';

import { NEW_ID } from './captures';

/** A monument within reach when a sample was taken, as the geometry and the photo saw it. */
export type SampleCandidate = {
  monumentId: string;
  distanceM: number;
  /** Degrees to turn to face it, negative to the left; none without a compass. */
  offsetDeg: number | null;
  inSight: boolean;
  geoScore: number;
  /** How much the photo looks like it; none without a photo or a reference photo. */
  likeness: number | null;
};

/** What the app would have done with the shot. */
export type SampleDecision = {
  kind: 'capture' | 'choose' | 'confirm' | 'nothing';
  /** The monument captured, or those offered to the player. */
  monumentIds: string[];
  /** Why nothing would have been captured. */
  reason: string | null;
};

/** A photo taken in collect mode, with its label (SPEC §8). */
export type NewSample = {
  id: string;
  /** When it was taken, as an ISO 8601 date in UTC. */
  takenAt: string;
  latitude: number;
  longitude: number;
  gpsAccuracyM: number;
  headingDeg: number | null;
  headingLevel: number | null;
  /** The name of the photo, in the folder of the samples; none without a camera. */
  photoFile: string | null;
  /** The vector of the photo; none without a photo. */
  vector: Float32Array | null;
  candidates: SampleCandidate[];
  decision: SampleDecision;
  /** The monument that the photo shows, as the player says; none for no monument of the app. */
  labelMonumentId: string | null;
  /** Taken from the side. */
  oblique: boolean;
  /** Partly hidden, by passers-by, trees or scaffolding. */
  hidden: boolean;
  bundleVersion: string;
  model: string;
  appVersion: string;
};

/** A sample as the collect screen lists it. */
export type SampleSummary = {
  id: string;
  takenAt: string;
  labelMonumentId: string | null;
};

/** A new identifier for a sample, the same kind as those of the captures. */
export async function newSampleId(db: SQLiteDatabase): Promise<string> {
  const row = await db.getFirstAsync<{ id: string }>(`select ${NEW_ID} as id`);
  if (row === null) {
    throw new Error('SQLite gave no identifier');
  }
  return row.id;
}

const INSERT = `
  insert into samples (
    id, taken_at, lat, lon, gps_accuracy_m, heading_deg, heading_level,
    photo_file, vector, candidates, decision, label_monument_id, oblique,
    hidden, bundle_version, model, app_version
  ) values (
    $id, $takenAt, $lat, $lon, $gpsAccuracyM, $headingDeg, $headingLevel,
    $photoFile, $vector, $candidates, $decision, $labelMonumentId, $oblique,
    $hidden, $bundleVersion, $model, $appVersion
  )
`;

export async function saveSample(db: SQLiteDatabase, sample: NewSample): Promise<void> {
  await db.runAsync(INSERT, {
    $id: sample.id,
    $takenAt: sample.takenAt,
    $lat: sample.latitude,
    $lon: sample.longitude,
    $gpsAccuracyM: sample.gpsAccuracyM,
    $headingDeg: sample.headingDeg,
    $headingLevel: sample.headingLevel,
    $photoFile: sample.photoFile,
    // The bytes of the 384 numbers, whatever buffer they are a view of.
    $vector:
      sample.vector === null
        ? null
        : new Uint8Array(sample.vector.buffer, sample.vector.byteOffset, sample.vector.byteLength).slice(),
    $candidates: JSON.stringify(sample.candidates),
    $decision: JSON.stringify(sample.decision),
    $labelMonumentId: sample.labelMonumentId,
    $oblique: sample.oblique ? 1 : 0,
    $hidden: sample.hidden ? 1 : 0,
    $bundleVersion: sample.bundleVersion,
    $model: sample.model,
    $appVersion: sample.appVersion,
  });
}

/** The samples taken so far, the latest first. */
export async function listSamples(db: SQLiteDatabase): Promise<SampleSummary[]> {
  return db.getAllAsync<SampleSummary>(
    `select id, taken_at as takenAt, label_monument_id as labelMonumentId
     from samples order by taken_at desc`,
  );
}
