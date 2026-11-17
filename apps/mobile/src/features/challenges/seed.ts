import type { SQLiteDatabase } from 'expo-sqlite';

const SEED = 'challenge_seed';

/**
 * The seed of the daily challenge of the player: 32 hexadecimal digits drawn
 * at the first start of the app and kept since. The server receives it once,
 * when the player joins the leaderboards, to draw the same places.
 */
export async function challengeSeed(db: SQLiteDatabase): Promise<string> {
  // Drawn in one statement: two callers at once keep the same seed.
  await db.runAsync(
    `insert into settings (key, value) values ($key, lower(hex(randomblob(16))))
     on conflict (key) do nothing`,
    { $key: SEED },
  );
  const row = await db.getFirstAsync<{ value: string }>(
    'select value from settings where key = $key',
    { $key: SEED },
  );
  if (row === null) {
    throw new Error('The seed of the daily challenge was not kept');
  }
  return row.value;
}
