import type { SQLiteDatabase } from 'expo-sqlite';

/** What the server made of a capture (supabase/migrations). */
export type RankStatus = 'accepted' | 'pending_review' | 'rejected';

/** A capture not sent to the leaderboards yet. */
export type UnrankedCapture = {
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
};

export type RankCounts = Record<RankStatus | 'waiting', number>;

/** The captures to send, the oldest first: the server checks each against the one before. */
export async function listUnranked(db: SQLiteDatabase): Promise<UnrankedCapture[]> {
  return db.getAllAsync<UnrankedCapture>(`
    select id, monument_id as monumentId, captured_at as capturedAt, lat, lon,
      gps_accuracy_m as gpsAccuracyM, heading_deg as headingDeg,
      heading_level as headingLevel, geo_score as geoScore, image_score as imageScore,
      chosen_by_player as chosenByPlayer
    from captures where ranked_at is null order by captured_at
  `);
}

export async function markRanked(
  db: SQLiteDatabase,
  id: string,
  status: RankStatus,
): Promise<void> {
  await db.runAsync(
    `update captures set ranked_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), rank_status = $status
     where id = $id`,
    { $id: id, $status: status },
  );
}

/** Forget what was sent, once the player has left the leaderboards. */
export async function forgetRanked(db: SQLiteDatabase): Promise<void> {
  await db.execAsync('update captures set ranked_at = null, rank_status = null');
}

/** How many captures the server accepted, holds for a review or refused, and how many wait. */
export async function countRanked(db: SQLiteDatabase): Promise<RankCounts> {
  const rows = await db.getAllAsync<{ status: string | null; count: number }>(
    'select rank_status as status, count(*) as count from captures group by rank_status',
  );
  const counts: RankCounts = { accepted: 0, pending_review: 0, rejected: 0, waiting: 0 };
  for (const row of rows) {
    if (row.status === null) {
      counts.waiting += row.count;
    } else if (row.status in counts) {
      counts[row.status as RankStatus] += row.count;
    }
  }
  return counts;
}
