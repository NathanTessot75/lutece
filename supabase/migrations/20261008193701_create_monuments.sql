-- Monuments and their reference photos, filled by the pipeline (SPEC §5.3).
-- PostGIS and pgvector live in the "extensions" schema.

create table public.monuments (
  id uuid primary key,
  merimee_id text not null unique,
  wikidata_qid text,
  osm_id text,
  name text not null,
  -- Not in the SPEC: 775 monuments are only called "Immeuble" or "Maison".
  address text,
  arrondissement smallint,
  location extensions.geography(point, 4326) not null,
  -- A multipolygon, not the polygon of the SPEC: 32 monuments are made of
  -- separate buildings.
  footprint extensions.geography(multipolygon, 4326),
  -- Not in the SPEC: tells a real outline from a 10 m circle around the point.
  footprint_source text,
  category text,
  -- Century of construction: 17 for the 17th century.
  period_start smallint,
  architects text[] not null default '{}',
  protection text not null,
  protection_desc text,
  visibility text not null default 'inconnu',
  rarity_score real,
  rarity_tier text,
  summary_fr text,
  story_fr text,
  sources jsonb not null default '[]'::jsonb,
  data_version integer not null,
  constraint monuments_protection_check
    check (protection in ('classé', 'inscrit')),
  constraint monuments_visibility_check
    check (visibility in ('visible', 'non_visible', 'inconnu')),
  constraint monuments_footprint_source_check
    check (footprint_source in ('osm_footprint', 'osm_line', 'osm_nearby', 'buffer')),
  constraint monuments_rarity_tier_check
    check (rarity_tier in ('commun', 'peu_commun', 'rare', 'légendaire'))
);

create index monuments_location_idx on public.monuments using gist (location);
create index monuments_footprint_idx on public.monuments using gist (footprint);

create table public.reference_images (
  id uuid primary key,
  monument_id uuid not null references public.monuments (id) on delete cascade,
  -- The page of the file, to credit its author.
  source_url text not null,
  -- Not in the SPEC: where to download the picture, the text of its licence,
  -- and its place among the photos of the monument.
  thumb_url text,
  author text,
  licence text,
  licence_url text,
  rank smallint,
  embedding extensions.vector(384),
  is_user_contributed boolean not null default false
);

create index reference_images_monument_id_idx
  on public.reference_images (monument_id);

-- The heritage data is public: anyone may read it, only the pipeline writes it.
alter table public.monuments enable row level security;
alter table public.reference_images enable row level security;

create policy "Monuments are readable by everyone"
  on public.monuments for select to anon, authenticated using (true);
create policy "Reference images are readable by everyone"
  on public.reference_images for select to anon, authenticated using (true);
