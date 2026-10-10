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
  merimeeId: string;
  address: string | null;
  architects: string[];
  wikidataQid: string | null;
  protection: string;
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
