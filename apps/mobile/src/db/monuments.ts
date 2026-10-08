import type { SQLiteDatabase } from 'expo-sqlite';

/** Whether the app can offer a monument to capture, as the pipeline decided. */
export type Readiness = 'ready' | 'approximate' | 'not_ready';

/** What a list shows of a monument. */
export type MonumentSummary = {
  id: string;
  title: string;
  arrondissement: number | null;
  category: string | null;
  century: number | null;
  readiness: Readiness;
};

const SUMMARIES = `
  select id, title, arrondissement, category, century, readiness
  from monuments
`;

export async function listMonuments(db: SQLiteDatabase): Promise<MonumentSummary[]> {
  return db.getAllAsync<MonumentSummary>(SUMMARIES);
}
