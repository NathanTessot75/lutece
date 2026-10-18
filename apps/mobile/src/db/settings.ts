import type { SQLiteDatabase } from 'expo-sqlite';

/** A setting of the player; none until it is set. */
export async function getSetting(db: SQLiteDatabase, key: string): Promise<string | null> {
  const row = await db.getFirstAsync<{ value: string }>(
    'select value from settings where key = $key',
    { $key: key },
  );
  return row?.value ?? null;
}

export async function setSetting(db: SQLiteDatabase, key: string, value: string): Promise<void> {
  await db.runAsync(
    'insert into settings (key, value) values ($key, $value) on conflict (key) do update set value = $value',
    { $key: key, $value: value },
  );
}
