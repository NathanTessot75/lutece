import type { SupabaseClient } from '@supabase/supabase-js';
import Constants from 'expo-constants';
import { File, Paths } from 'expo-file-system';
import { ImageManipulator, SaveFormat } from 'expo-image-manipulator';
import type { SQLiteDatabase } from 'expo-sqlite';

import {
  forgetSent,
  listUnsentCaptures,
  listUnsentSamples,
  markSent,
} from '@/db/contributions';
import { fitWithin } from '@/features/collect/sample';
import { signedInPlayer } from '@/lib/supabase';

import { type ContributionRow, captureRow, photoPath, sampleRow } from './rows';

const BUCKET = 'contributions';
// Where the app keeps the photos of the samples and of the captures.
const SAMPLE_FOLDER = 'samples';
const CAPTURE_FOLDER = 'captures';
// A row that the server already has: sent before, the answer lost on the way.
const ALREADY_RECEIVED = '23505';
// As the photos of the samples: the camera's own file is too heavy for the bucket.
const QUALITY = 0.85;

/** The bytes of a photo, its longest side brought down to the size of a sample. */
async function lighter(file: File): Promise<Uint8Array> {
  const original = await ImageManipulator.manipulate(file.uri).renderAsync();
  const size = fitWithin(original.width, original.height);
  if (size === null) {
    return file.bytes();
  }
  const resized = await ImageManipulator.manipulate(original).resize(size).renderAsync();
  const saved = await resized.saveAsync({ format: SaveFormat.JPEG, compress: QUALITY });
  const copy = new File(saved.uri);
  try {
    return await copy.bytes();
  } finally {
    copy.delete();
  }
}

/** Send a photo, unless the server has it already. Tells whether it is there. */
async function sendPhoto(client: SupabaseClient, path: string, file: File | null): Promise<boolean> {
  if (file === null || !file.exists) {
    return false;
  }
  const bytes = await lighter(file);
  const { error } = await client.storage
    .from(BUCKET)
    .upload(path, bytes.slice().buffer, { contentType: 'image/jpeg', upsert: false });
  if (error && !/exists/i.test(error.message)) {
    throw error;
  }
  return true;
}

async function sendRow(client: SupabaseClient, row: ContributionRow): Promise<void> {
  const { error } = await client.from('contributions').insert(row);
  if (error && error.code !== ALREADY_RECEIVED) {
    throw error;
  }
}

/**
 * Send every sample and capture that the server has not received yet, the
 * photo first, then its row. Stops at the first failure, or when the player
 * stops contributing: the rest waits for the next attempt.
 */
export async function sendPending(
  client: SupabaseClient,
  db: SQLiteDatabase,
  keepGoing: () => boolean,
): Promise<number> {
  const userId = await signedInPlayer(client);
  const appVersion = Constants.expoConfig?.version ?? 'unknown';
  let sent = 0;
  for (const sample of await listUnsentSamples(db)) {
    if (!keepGoing()) {
      return sent;
    }
    const photo = sample.photoFile ? new File(Paths.document, SAMPLE_FOLDER, sample.photoFile) : null;
    const withPhoto = await sendPhoto(client, photoPath(userId, sample.id), photo);
    await sendRow(client, sampleRow(sample, userId, withPhoto));
    await markSent(db, 'samples', sample.id);
    sent++;
  }
  for (const capture of await listUnsentCaptures(db)) {
    if (!keepGoing()) {
      return sent;
    }
    const photo = capture.photoFile
      ? new File(Paths.document, CAPTURE_FOLDER, capture.photoFile)
      : null;
    const withPhoto = await sendPhoto(client, photoPath(userId, capture.id), photo);
    await sendRow(client, captureRow(capture, userId, withPhoto, appVersion));
    await markSent(db, 'captures', capture.id);
    sent++;
  }
  return sent;
}

/** Delete from the server all that this player has sent, photos and rows. */
export async function deleteContributions(
  client: SupabaseClient,
  db: SQLiteDatabase,
): Promise<void> {
  const { data } = await client.auth.getSession();
  const userId = data.session?.user.id;
  if (userId) {
    for (;;) {
      const { data: files, error } = await client.storage.from(BUCKET).list(userId, { limit: 100 });
      if (error) {
        throw error;
      }
      if (files.length === 0) {
        break;
      }
      const { data: removed, error: removing } = await client.storage
        .from(BUCKET)
        .remove(files.map((file) => `${userId}/${file.name}`));
      if (removing) {
        throw removing;
      }
      if (removed.length === 0) {
        throw new Error('The server kept the photos');
      }
    }
    const { error } = await client.from('contributions').delete().eq('user_id', userId);
    if (error) {
      throw error;
    }
  }
  await forgetSent(db);
}
