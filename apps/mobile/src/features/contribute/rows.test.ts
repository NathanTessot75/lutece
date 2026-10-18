import type { UnsentCapture, UnsentSample } from '@/db/contributions';

import { CONSENT_VERSION, captureRow, photoPath, sampleRow } from './rows';

const PLAYER = '6f1c2a40-0000-4000-8000-000000000001';

function blob(numbers: number[]): Uint8Array {
  return new Uint8Array(new Float32Array(numbers).buffer);
}

const SAMPLE: UnsentSample = {
  id: 'a3f0c1d2-0000-4000-8000-00000000000a',
  takenAt: '2026-10-18T14:02:11.120Z',
  lat: 48.853,
  lon: 2.3499,
  gpsAccuracyM: 6,
  headingDeg: 214.5,
  headingLevel: 3,
  photoFile: 'a3f0c1d2-0000-4000-8000-00000000000a.jpg',
  vector: blob([0.5, -0.25, 0.125]),
  candidates: JSON.stringify([{ monumentId: 'notre-dame', distanceM: 80, likeness: 0.7 }]),
  decision: JSON.stringify({ kind: 'capture', monumentIds: ['notre-dame'], reason: null }),
  labelMonumentId: 'notre-dame',
  oblique: 1,
  hidden: 0,
  bundleVersion: 'd7eb8420d465',
  model: '056d387b1e31',
  appVersion: '1.0.0',
};

const CAPTURE: UnsentCapture = {
  id: 'b4e1d2c3-0000-4000-8000-00000000000b',
  monumentId: 'pantheon',
  capturedAt: '2026-10-18T15:30:00.000Z',
  lat: 48.8462,
  lon: 2.3464,
  gpsAccuracyM: 9,
  headingDeg: null,
  headingLevel: null,
  geoScore: 0.82,
  imageScore: 0.81,
  chosenByPlayer: 0,
  photoFile: 'pantheon.jpg',
};

describe('photoPath', () => {
  it('puts the photo in the folder of its player', () => {
    expect(photoPath(PLAYER, SAMPLE.id)).toBe(`${PLAYER}/${SAMPLE.id}.jpg`);
  });
});

describe('sampleRow', () => {
  it('sends all that the phone knew, the label as the monument', () => {
    const row = sampleRow(SAMPLE, PLAYER, true);
    expect(row).toMatchObject({
      id: SAMPLE.id,
      user_id: PLAYER,
      kind: 'sample',
      taken_at: SAMPLE.takenAt,
      heading_level: 3,
      photo_path: `${PLAYER}/${SAMPLE.id}.jpg`,
      vector: [0.5, -0.25, 0.125],
      monument_id: 'notre-dame',
      oblique: true,
      hidden: false,
      consent_version: CONSENT_VERSION,
    });
    expect(row.candidates).toEqual([{ monumentId: 'notre-dame', distanceM: 80, likeness: 0.7 }]);
    expect(row.decision).toEqual({ kind: 'capture', monumentIds: ['notre-dame'], reason: null });
  });

  it('reads the vector from bytes that do not start the buffer', () => {
    const bytes = blob([9, 0.5, -0.25]).subarray(4);
    expect(sampleRow({ ...SAMPLE, vector: bytes }, PLAYER, true).vector).toEqual([0.5, -0.25]);
  });

  it('leaves out what the sample lacks', () => {
    const row = sampleRow({ ...SAMPLE, vector: null, labelMonumentId: null }, PLAYER, false);
    expect(row.photo_path).toBeNull();
    expect(row.vector).toBeNull();
    expect(row.monument_id).toBeNull();
  });
});

describe('captureRow', () => {
  it('sends the monument and the scores of the capture', () => {
    const row = captureRow(CAPTURE, PLAYER, true, '1.0.0');
    expect(row).toMatchObject({
      id: CAPTURE.id,
      kind: 'capture',
      taken_at: CAPTURE.capturedAt,
      photo_path: `${PLAYER}/${CAPTURE.id}.jpg`,
      monument_id: 'pantheon',
      chosen_by_player: false,
      geo_score: 0.82,
      image_score: 0.81,
      heading_deg: null,
      candidates: [],
      decision: null,
      app_version: '1.0.0',
    });
  });

  it('sends a capture without its photo when the photo is gone', () => {
    expect(captureRow(CAPTURE, PLAYER, false, '1.0.0').photo_path).toBeNull();
  });
});
