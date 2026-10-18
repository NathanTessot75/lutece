import type { SupabaseClient } from '@supabase/supabase-js';
import type { SQLiteDatabase } from 'expo-sqlite';

import { type RankStatus, forgetRanked, listUnranked, markRanked } from '@/db/ranking';
import { signedInPlayer } from '@/lib/supabase';

// The version of the text the player agreed to; a new text, a new version.
export const LEADERBOARD_CONSENT_VERSION = '2026-10-19';

// Errors of Postgres the app expects (supabase/migrations).
const TAKEN = '23505';
const NOT_A_PSEUDONYM = '23514';
// A place that the server does not know yet: its seed is older than the bundle.
const NO_PLACE = 'P0002';

/** Why a pseudonym was not kept, in words for the player. */
export class PseudonymRefused extends Error {}

/** A row of the leaderboard. */
export type Standing = {
  rank: number;
  username: string;
  points: number;
  captures: number;
  isMe: boolean;
};

/** Join the leaderboards under a pseudonym, or change it. */
export async function joinLeaderboards(client: SupabaseClient, username: string): Promise<void> {
  const id = await signedInPlayer(client);
  const { error } = await client.from('profiles').upsert({ id, username });
  if (error?.code === TAKEN) {
    throw new PseudonymRefused('Ce pseudonyme est déjà pris.');
  }
  if (error?.code === NOT_A_PSEUDONYM) {
    throw new PseudonymRefused('Un pseudonyme a de 3 à 20 caractères.');
  }
  if (error) {
    throw error;
  }
}

/**
 * Send every capture that the leaderboards have not received yet, the oldest
 * first. Stops at the first failure, or when the player leaves: the rest
 * waits for the next attempt.
 */
export async function sendRankings(
  client: SupabaseClient,
  db: SQLiteDatabase,
  keepGoing: () => boolean,
): Promise<void> {
  await signedInPlayer(client);
  for (const capture of await listUnranked(db)) {
    if (!keepGoing()) {
      return;
    }
    const { data, error } = await client.rpc('submit_capture', {
      capture_id: capture.id,
      monument: capture.monumentId,
      taken_at: capture.capturedAt,
      lat: capture.lat,
      lon: capture.lon,
      accuracy_m: capture.gpsAccuracyM,
      heading_deg: capture.headingDeg,
      heading_level: capture.headingLevel,
      geo_score: capture.geoScore,
      image_score: capture.imageScore,
      chosen_by_player: capture.chosenByPlayer === 1,
    });
    if (error?.code === NO_PLACE) {
      continue;
    }
    if (error) {
      throw error;
    }
    await markRanked(db, capture.id, data as RankStatus);
  }
}

/** Leave the leaderboards: the server deletes the profile and the captures with it. */
export async function leaveLeaderboards(client: SupabaseClient, db: SQLiteDatabase): Promise<void> {
  const id = await signedInPlayer(client);
  const { error } = await client.from('profiles').delete().eq('id', id);
  if (error) {
    throw error;
  }
  await forgetRanked(db);
}

type StandingRow = {
  rank: number;
  username: string;
  points: number;
  captures: number;
  is_me: boolean;
};

/** The leaderboard of Paris, or of an arrondissement. */
export async function fetchLeaderboard(
  client: SupabaseClient,
  arrondissement: number | null,
): Promise<Standing[]> {
  await signedInPlayer(client);
  const { data, error } = await client.rpc('leaderboard', {
    in_arrondissement: arrondissement,
    size: 50,
  });
  if (error) {
    throw error;
  }
  return (data as StandingRow[]).map((row) => ({
    rank: Number(row.rank),
    username: row.username,
    points: Number(row.points),
    captures: Number(row.captures),
    isMe: row.is_me,
  }));
}
