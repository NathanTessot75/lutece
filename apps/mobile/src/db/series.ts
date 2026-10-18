import type { SQLiteDatabase } from 'expo-sqlite';

/** A thematic series of places to complete (SPEC §2). */
export type Series = {
  slug: string;
  name: string;
  description: string;
};

/** The places that can be captured in each series and each arrondissement. */
export type Groups = {
  series: (Series & { ids: string[] })[];
  arrondissements: { arrondissement: number; ids: string[] }[];
};

// A place that can only be looked at counts in no group.
const SERIES = 'select slug, name, description from series order by position';
const MEMBERS = `
  select ms.series_slug as slug, ms.monument_id as id
  from monument_series ms join monuments m on m.id = ms.monument_id
  where m.readiness <> 'not_ready'
`;
const PLACES = `
  select id, arrondissement from monuments
  where readiness <> 'not_ready' and arrondissement is not null
  order by arrondissement
`;

export async function loadGroups(db: SQLiteDatabase): Promise<Groups> {
  const [series, members, places] = await Promise.all([
    db.getAllAsync<Series>(SERIES),
    db.getAllAsync<{ slug: string; id: string }>(MEMBERS),
    db.getAllAsync<{ id: string; arrondissement: number }>(PLACES),
  ]);
  const bySlug = new Map<string, string[]>();
  for (const member of members) {
    bySlug.set(member.slug, [...(bySlug.get(member.slug) ?? []), member.id]);
  }
  const byNumber = new Map<number, string[]>();
  for (const place of places) {
    byNumber.set(place.arrondissement, [...(byNumber.get(place.arrondissement) ?? []), place.id]);
  }
  return {
    series: series.map((one) => ({ ...one, ids: bySlug.get(one.slug) ?? [] })),
    arrondissements: [...byNumber].map(([arrondissement, ids]) => ({ arrondissement, ids })),
  };
}
