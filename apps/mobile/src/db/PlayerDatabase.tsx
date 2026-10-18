import { type SQLiteDatabase, openDatabaseAsync } from 'expo-sqlite';
import { type ReactNode, createContext, use } from 'react';

// What the player does lives in its own database: the one of the monuments
// is replaced whenever the pipeline publishes a new bundle.
const PLAYER_DATABASE_NAME = 'player.db';

// Each entry brings the database from one version to the next. An entry is
// never edited once an app has shipped with it: a change is a new entry.
const MIGRATIONS = [
  `
  create table captures (
    id text primary key,
    monument_id text not null unique,
    captured_at text not null,
    lat real not null,
    lon real not null,
    gps_accuracy_m real not null,
    heading_deg real,
    heading_level integer,
    geo_score real not null,
    image_score real,
    final_score real not null,
    status text not null check (status in ('accepted', 'pending_review', 'rejected')),
    chosen_by_player integer not null,
    photo_file text
  ) strict;
  `,
  `
  create table settings (
    key text primary key,
    value text not null
  ) strict;

  -- A photo taken in collect mode and labelled by the player: the field test
  -- set (SPEC §8), with all that the app knew and would have decided.
  create table samples (
    id text primary key,
    taken_at text not null,
    lat real not null,
    lon real not null,
    gps_accuracy_m real not null,
    heading_deg real,
    heading_level integer,
    photo_file text,
    vector blob,
    candidates text not null,
    decision text not null,
    label_monument_id text,
    oblique integer not null,
    hidden integer not null,
    bundle_version text not null,
    model text not null,
    app_version text not null
  ) strict;
  `,
];

async function migrate(db: SQLiteDatabase): Promise<void> {
  const row = await db.getFirstAsync<{ user_version: number }>('pragma user_version');
  for (let version = row?.user_version ?? 0; version < MIGRATIONS.length; version++) {
    await db.withTransactionAsync(async () => {
      await db.execAsync(MIGRATIONS[version]);
      await db.execAsync(`pragma user_version = ${version + 1}`);
    });
  }
}

async function open(): Promise<SQLiteDatabase> {
  const db = await openDatabaseAsync(PLAYER_DATABASE_NAME);
  await migrate(db);
  return db;
}

let opening: Promise<SQLiteDatabase> | undefined;

const PlayerDatabaseContext = createContext<SQLiteDatabase | null>(null);

/** Open the database of the player once, and wait for it under a `Suspense`. */
export function PlayerDatabaseProvider({ children }: { children: ReactNode }) {
  opening ??= open();
  const db = use(opening);
  return <PlayerDatabaseContext value={db}>{children}</PlayerDatabaseContext>;
}

export function usePlayerDatabase(): SQLiteDatabase {
  const db = use(PlayerDatabaseContext);
  if (db === null) {
    throw new Error('usePlayerDatabase must be used under a PlayerDatabaseProvider');
  }
  return db;
}
