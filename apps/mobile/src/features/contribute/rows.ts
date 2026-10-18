import type { UnsentCapture, UnsentSample } from '@/db/contributions';

/**
 * The version of the text that a player agrees to when turning the
 * contribution on: each contribution records it. A new text, a new version.
 */
export const CONSENT_VERSION = '2026-10-18';

/** A contribution as the table of the server receives it (supabase/migrations). */
export type ContributionRow = {
  id: string;
  user_id: string;
  kind: 'sample' | 'capture';
  taken_at: string;
  lat: number;
  lon: number;
  gps_accuracy_m: number;
  heading_deg: number | null;
  heading_level: number | null;
  photo_path: string | null;
  vector: number[] | null;
  candidates: unknown[];
  decision: unknown;
  monument_id: string | null;
  chosen_by_player: boolean | null;
  geo_score: number | null;
  image_score: number | null;
  oblique: boolean | null;
  hidden: boolean | null;
  bundle_version: string | null;
  model: string | null;
  app_version: string;
  consent_version: string;
};

/** Where the photo of a contribution goes on the server: the folder of its player. */
export function photoPath(userId: string, id: string): string {
  return `${userId}/${id}.jpg`;
}

/** The numbers of a vector from the bytes the player database keeps. */
function toNumbers(blob: Uint8Array): number[] {
  const copy = blob.slice();
  return Array.from(new Float32Array(copy.buffer, 0, copy.byteLength / 4));
}

export function sampleRow(
  sample: UnsentSample,
  userId: string,
  withPhoto: boolean,
): ContributionRow {
  return {
    id: sample.id,
    user_id: userId,
    kind: 'sample',
    taken_at: sample.takenAt,
    lat: sample.lat,
    lon: sample.lon,
    gps_accuracy_m: sample.gpsAccuracyM,
    heading_deg: sample.headingDeg,
    heading_level: sample.headingLevel,
    photo_path: withPhoto ? photoPath(userId, sample.id) : null,
    vector: sample.vector === null ? null : toNumbers(sample.vector),
    candidates: JSON.parse(sample.candidates) as unknown[],
    decision: JSON.parse(sample.decision) as unknown,
    monument_id: sample.labelMonumentId,
    chosen_by_player: null,
    geo_score: null,
    image_score: null,
    oblique: sample.oblique === 1,
    hidden: sample.hidden === 1,
    bundle_version: sample.bundleVersion,
    model: sample.model,
    app_version: sample.appVersion,
    consent_version: CONSENT_VERSION,
  };
}

export function captureRow(
  capture: UnsentCapture,
  userId: string,
  withPhoto: boolean,
  appVersion: string,
): ContributionRow {
  return {
    id: capture.id,
    user_id: userId,
    kind: 'capture',
    taken_at: capture.capturedAt,
    lat: capture.lat,
    lon: capture.lon,
    gps_accuracy_m: capture.gpsAccuracyM,
    heading_deg: capture.headingDeg,
    heading_level: capture.headingLevel,
    photo_path: withPhoto ? photoPath(userId, capture.id) : null,
    vector: null,
    candidates: [],
    decision: null,
    monument_id: capture.monumentId,
    chosen_by_player: capture.chosenByPlayer === 1,
    geo_score: capture.geoScore,
    image_score: capture.imageScore,
    oblique: null,
    hidden: null,
    bundle_version: null,
    model: null,
    app_version: appVersion,
    consent_version: CONSENT_VERSION,
  };
}
