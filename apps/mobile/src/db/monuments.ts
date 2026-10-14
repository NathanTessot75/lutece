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

export type Visibility = 'visible' | 'non_visible' | 'inconnu';

/** Everything the page of a monument says about it. */
export type MonumentDetails = MonumentSummary & {
  /** The notice of a protected monument; none for a place that is not one. */
  merimeeId: string | null;
  address: string | null;
  architects: string[];
  wikidataQid: string | null;
  /** The title of the article of the French Wikipedia that speaks of it. */
  wikipedia: string | null;
  /** « classé » or « inscrit »; none for a place that is not protected. */
  protection: string | null;
  visibility: Visibility;
};

/** A photo of a monument on Wikimedia Commons, with what its licence asks to show. */
export type MonumentPhoto = {
  rank: number;
  thumbUrl: string;
  pageUrl: string;
  author: string | null;
  licence: string | null;
};

/** A monument and the point where the map marks it. */
export type MonumentPlace = MonumentSummary & {
  lat: number;
  lon: number;
};

/** The height and width, in degrees, of the squares that the map groups monuments by. */
export type Grid = {
  latStep: number;
  lonStep: number;
};

/** Whole squares of a grid, from one corner to the other. */
export type CellRange = {
  firstRow: number;
  lastRow: number;
  firstColumn: number;
  lastColumn: number;
};

/** The monuments of one square: how many, around which point, and which one when alone. */
export type MonumentCell = {
  row: number;
  column: number;
  count: number;
  lat: number;
  lon: number;
  monument: MonumentPlace | null;
};

/** A monument that can be captured, with what tells whether it is aimed at. */
export type CapturableMonument = MonumentSummary & {
  /** How far it may be captured from, in metres, whatever the accuracy of the GPS. */
  reachM: number;
  /** Its outline, as the GeoJSON multipolygon that the pipeline wrote. */
  footprint: string;
};

export type Bounds = {
  south: number;
  north: number;
  west: number;
  east: number;
};

const SUMMARIES = `
  select id, title, arrondissement, category, century, readiness
  from monuments
`;

const PLACES = `
  select id, title, arrondissement, category, century, readiness, lat, lon
  from monuments
  where lat between $south and $north and lon between $west and $east
`;

// Paris lies north and east of the origin, so truncating is rounding down.
// The columns of a monument are only read from a square that holds one.
const CELLS = `
  select
    cast(lat / $latStep as integer) as cell_row,
    cast(lon / $lonStep as integer) as cell_column,
    count(*) as count,
    avg(lat) as lat,
    avg(lon) as lon,
    min(id) as id,
    min(title) as title,
    min(arrondissement) as arrondissement,
    min(category) as category,
    min(century) as century,
    min(readiness) as readiness
  from monuments
  where cast(lat / $latStep as integer) between $firstRow and $lastRow
    and cast(lon / $lonStep as integer) between $firstColumn and $lastColumn
  group by cell_row, cell_column
`;

const FOOTPRINT = 'select footprint from monuments where id = $id';

const DETAILS = `
  select
    id, title, arrondissement, category, century, readiness,
    merimee_id as merimeeId,
    address,
    architects,
    wikidata_qid as wikidataQid,
    wikipedia,
    protection,
    visibility
  from monuments
  where id = $id
`;

const PHOTOS = `
  select rank, thumb_url as thumbUrl, page_url as pageUrl, author, licence
  from photos
  where monument_id = $id
  order by rank
`;

// The box of each footprint, widened by the distance at which the monument
// may be captured, tells whether a place is close enough to consider it.
const CAPTURABLE_AROUND = `
  select
    id, title, arrondissement, category, century, readiness,
    capture_reach_m as reachM,
    footprint
  from monuments
  where readiness <> 'not_ready'
    and $lat between min_lat - (max(capture_reach_m, $leastReach) + $margin) / $metresPerLat
                 and max_lat + (max(capture_reach_m, $leastReach) + $margin) / $metresPerLat
    and $lon between min_lon - (max(capture_reach_m, $leastReach) + $margin) / $metresPerLon
                 and max_lon + (max(capture_reach_m, $leastReach) + $margin) / $metresPerLon
`;

const METRES_PER_DEGREE = 111_195;

// The bundle writes the architects as a JSON array.
type DetailsRow = Omit<MonumentDetails, 'architects'> & { architects: string };

type CellRow = MonumentPlace & {
  cell_row: number;
  cell_column: number;
  count: number;
};

export async function listMonuments(db: SQLiteDatabase): Promise<MonumentSummary[]> {
  return db.getAllAsync<MonumentSummary>(SUMMARIES);
}

/** Every monument marked inside the bounds. */
export async function listPlaces(db: SQLiteDatabase, bounds: Bounds): Promise<MonumentPlace[]> {
  return db.getAllAsync<MonumentPlace>(PLACES, {
    $south: bounds.south,
    $north: bounds.north,
    $west: bounds.west,
    $east: bounds.east,
  });
}

/** The squares of the grid that hold monuments, each counted once and whole. */
export async function listCells(
  db: SQLiteDatabase,
  grid: Grid,
  range: CellRange,
): Promise<MonumentCell[]> {
  const rows = await db.getAllAsync<CellRow>(CELLS, {
    $latStep: grid.latStep,
    $lonStep: grid.lonStep,
    $firstRow: range.firstRow,
    $lastRow: range.lastRow,
    $firstColumn: range.firstColumn,
    $lastColumn: range.lastColumn,
  });
  return rows.map(({ cell_row, cell_column, count, ...place }) => ({
    row: cell_row,
    column: cell_column,
    count,
    lat: place.lat,
    lon: place.lon,
    monument: count === 1 ? place : null,
  }));
}

/** The outline of a monument, as the GeoJSON multipolygon that the pipeline wrote. */
export async function getFootprint(db: SQLiteDatabase, id: string): Promise<string | null> {
  const row = await db.getFirstAsync<{ footprint: string }>(FOOTPRINT, { $id: id });
  return row?.footprint ?? null;
}

export async function getMonument(db: SQLiteDatabase, id: string): Promise<MonumentDetails | null> {
  const row = await db.getFirstAsync<DetailsRow>(DETAILS, { $id: id });
  return row && { ...row, architects: JSON.parse(row.architects) as string[] };
}

/** The photos of a monument, the best one first. */
export async function listPhotos(db: SQLiteDatabase, id: string): Promise<MonumentPhoto[]> {
  return db.getAllAsync<MonumentPhoto>(PHOTOS, { $id: id });
}

/**
 * The monuments that may be captured from a place or from `marginM` around it.
 * `leastReachM` is the distance within which any monument can be captured.
 */
export async function listCapturableAround(
  db: SQLiteDatabase,
  place: { latitude: number; longitude: number },
  leastReachM: number,
  marginM: number,
): Promise<CapturableMonument[]> {
  return db.getAllAsync<CapturableMonument>(CAPTURABLE_AROUND, {
    $lat: place.latitude,
    $lon: place.longitude,
    $leastReach: leastReachM,
    $margin: marginM,
    $metresPerLat: METRES_PER_DEGREE,
    $metresPerLon: METRES_PER_DEGREE * Math.cos((place.latitude * Math.PI) / 180),
  });
}

/** The monuments with these identifiers, in no particular order. */
export async function listMonumentsByIds(
  db: SQLiteDatabase,
  ids: readonly string[],
): Promise<MonumentSummary[]> {
  if (ids.length === 0) {
    return [];
  }
  const marks = ids.map(() => '?').join(', ');
  return db.getAllAsync<MonumentSummary>(`${SUMMARIES} where id in (${marks})`, [...ids]);
}

/** How many monuments the bundle offers to capture. */
export async function countCapturable(db: SQLiteDatabase): Promise<number> {
  const row = await db.getFirstAsync<{ count: number }>(
    "select count(*) as count from monuments where readiness <> 'not_ready'",
  );
  return row?.count ?? 0;
}

/** The vector of a reference photo, written on 8 bits in the bundle. */
export type ReferenceVector = {
  rank: number;
  /** Multiplied by `scale`, the bytes make a vector of length 1. */
  scale: number;
  levels: Int8Array;
};

type VectorRow = { monumentId: string; rank: number; scale: number; vector: Uint8Array };

/** Read the bytes of a vector as SQLite gives them. */
function toLevels(blob: Uint8Array): Int8Array {
  return new Int8Array(blob.buffer, blob.byteOffset, blob.byteLength);
}

/** The vectors of the reference photos of these monuments, by monument. */
export async function listReferenceVectors(
  db: SQLiteDatabase,
  ids: readonly string[],
): Promise<Map<string, ReferenceVector[]>> {
  const vectors = new Map<string, ReferenceVector[]>();
  if (ids.length === 0) {
    return vectors;
  }
  const marks = ids.map(() => '?').join(', ');
  const rows = await db.getAllAsync<VectorRow>(
    `select monument_id as monumentId, rank, scale, vector from reference_vectors
     where monument_id in (${marks}) order by monument_id, rank`,
    [...ids],
  );
  for (const row of rows) {
    const list = vectors.get(row.monumentId) ?? [];
    list.push({ rank: row.rank, scale: row.scale, levels: toLevels(row.vector) });
    vectors.set(row.monumentId, list);
  }
  return vectors;
}

/** A first photo of a monument, with the vector that the pipeline gave it. */
export type ReferenceSample = ReferenceVector & {
  id: string;
  title: string;
  thumbUrl: string;
};

/** The first photos of `count` monuments, always the same, with their vectors. */
export async function listReferenceSamples(
  db: SQLiteDatabase,
  count: number,
): Promise<ReferenceSample[]> {
  const rows = await db.getAllAsync<Omit<VectorRow, 'monumentId'> & ReferenceSample>(
    `select m.id, m.title, p.thumb_url as thumbUrl, v.rank, v.scale, v.vector
     from photos p
     join reference_vectors v on v.monument_id = p.monument_id and v.rank = p.rank
     join monuments m on m.id = p.monument_id
     where p.rank = 1
     order by m.id
     limit $count`,
    { $count: count },
  );
  return rows.map(({ vector, ...row }) => ({ ...row, levels: toLevels(vector) }));
}
