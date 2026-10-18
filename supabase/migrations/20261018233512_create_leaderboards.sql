-- The leaderboards (phase 5): players who join under a pseudonym send their
-- captures, which the server checks before counting them (SPEC §7). Players
-- sign in anonymously; a player reaches only their own profile and captures,
-- and sees the others only through the leaderboard: pseudonym, points and
-- number of captures, never where or when.

-- The places of the app, as the bundle has them: the pipeline writes them in
-- supabase/seeds/places.sql. Only the functions below read them.
create table public.places (
  id uuid primary key,
  title text not null,
  location extensions.geography(point, 4326) not null,
  footprint extensions.geography(multipolygon, 4326) not null,
  -- How far it may be captured from, set by hand; 0 when the GPS alone decides.
  reach_m integer not null default 0,
  arrondissement smallint,
  rarity_tier text,
  bundle_version text not null,
  constraint places_rarity_tier_check
    check (rarity_tier in ('commun', 'peu_commun', 'rare', 'légendaire'))
);

create index places_footprint_idx on public.places using gist (footprint);

alter table public.places enable row level security;

create table public.profiles (
  id uuid primary key default auth.uid() references auth.users (id) on delete cascade,
  username text not null,
  created_at timestamptz not null default now(),
  constraint profiles_username_check check (
    username = btrim(username)
    and char_length(username) between 3 and 20
    and username !~ '[[:cntrl:]]'
  )
);

-- One pseudonym per player, whatever its capitals.
create unique index profiles_username_key on public.profiles (lower(username));

alter table public.profiles enable row level security;

create policy "Players read their own profile"
  on public.profiles for select to authenticated
  using (id = (select auth.uid()));

create policy "Players create their own profile"
  on public.profiles for insert to authenticated
  with check (id = (select auth.uid()));

create policy "Players rename themselves"
  on public.profiles for update to authenticated
  using (id = (select auth.uid()))
  with check (id = (select auth.uid()));

-- Leaving the leaderboards deletes the profile and, with it, the captures.
create policy "Players leave the leaderboards"
  on public.profiles for delete to authenticated
  using (id = (select auth.uid()));

-- The SPEC §5.3 table, without the scores that only the phone can compute.
create table public.captures (
  -- The identifier of the capture on the phone.
  id uuid primary key,
  user_id uuid not null references public.profiles (id) on delete cascade,
  monument_id uuid not null references public.places (id),
  captured_at timestamptz not null,
  lat double precision not null,
  lon double precision not null,
  gps_accuracy_m real not null,
  heading_deg real,
  heading_level smallint,
  geo_score real,
  image_score real,
  chosen_by_player boolean not null default false,
  -- From the rarity of the place on the server, not from the phone.
  points integer not null,
  status text not null,
  -- Why a capture waits for a review, or was refused.
  reason text,
  -- From the position of the player to the outline of the place.
  distance_m real not null,
  received_at timestamptz not null default now(),
  constraint captures_once unique (user_id, monument_id),
  constraint captures_status_check
    check (status in ('accepted', 'pending_review', 'rejected')),
  constraint captures_reason_check
    check (reason in ('future', 'far', 'too_far', 'too_fast', 'too_many'))
);

create index captures_user_id_idx on public.captures (user_id, captured_at);
create index captures_monument_id_idx on public.captures (monument_id);

alter table public.captures enable row level security;

create policy "Players read their own captures"
  on public.captures for select to authenticated
  using (user_id = (select auth.uid()));

create policy "Players delete their own captures"
  on public.captures for delete to authenticated
  using (user_id = (select auth.uid()));

-- Check a capture and keep it: accepted, waiting for a review by hand, or
-- refused. The thresholds are provisional (decision of 19 October 2026). A
-- capture sent twice is kept once and keeps its first verdict.
create function public.submit_capture(
  capture_id uuid,
  monument uuid,
  taken_at timestamptz,
  lat double precision,
  lon double precision,
  accuracy_m real,
  heading_deg real default null,
  heading_level smallint default null,
  geo_score real default null,
  image_score real default null,
  chosen_by_player boolean default false
) returns text
language plpgsql
security definer
set search_path = ''
as $$
declare
  player uuid := auth.uid();
  place public.places;
  here extensions.geography;
  away real;
  allowed real;
  before record;
  hours double precision;
  same_day integer;
  verdict text := 'accepted';
  why text;
  known text;
begin
  if player is null or not exists (select 1 from public.profiles where id = player) then
    raise exception 'Join the leaderboards first' using errcode = '42501';
  end if;
  select status into known
    from public.captures where user_id = player and captures.monument_id = monument;
  if found then
    return known;
  end if;
  select * into place from public.places where id = monument;
  if not found then
    raise exception 'No place %', monument using errcode = 'P0002';
  end if;

  here := extensions.st_setsrid(extensions.st_makepoint(lon, lat), 4326)::extensions.geography;
  away := extensions.st_distance(here, place.footprint);
  -- The reach of the app, at least 150 m, widened by the accuracy of the GPS.
  allowed := greatest(place.reach_m, 150) + least(greatest(accuracy_m, 0), 100);

  if taken_at > now() + interval '10 minutes' then
    verdict := 'rejected';
    why := 'future';
  elsif away > 2 * allowed then
    verdict := 'rejected';
    why := 'too_far';
  elsif away > allowed then
    verdict := 'pending_review';
    why := 'far';
  end if;

  if verdict = 'accepted' then
    select c.captured_at, c.lat, c.lon into before
      from public.captures c
      where c.user_id = player and c.captured_at <= taken_at and c.status <> 'rejected'
      order by c.captured_at desc
      limit 1;
    if found then
      -- At least a minute between two captures: the GPS wanders by a few
      -- metres between monuments taken one after the other.
      hours := greatest(extract(epoch from taken_at - before.captured_at), 60) / 3600;
      if extensions.st_distance(
        extensions.st_setsrid(extensions.st_makepoint(before.lon, before.lat), 4326)::extensions.geography,
        here
      ) / 1000 / hours > 60 then
        verdict := 'pending_review';
        why := 'too_fast';
      end if;
    end if;
  end if;

  if verdict = 'accepted' then
    select count(*) into same_day
      from public.captures c
      where c.user_id = player
        and (c.captured_at at time zone 'Europe/Paris')::date
          = (taken_at at time zone 'Europe/Paris')::date;
    if same_day >= 30 then
      verdict := 'pending_review';
      why := 'too_many';
    end if;
  end if;

  insert into public.captures (
    id, user_id, monument_id, captured_at, lat, lon, gps_accuracy_m, heading_deg,
    heading_level, geo_score, image_score, chosen_by_player, points, status, reason,
    distance_m
  ) values (
    capture_id, player, monument, taken_at, lat, lon, accuracy_m, heading_deg,
    heading_level, geo_score, image_score, coalesce(chosen_by_player, false),
    -- As the app counts them (apps/mobile/src/features/game/rarity.ts).
    case place.rarity_tier
      when 'légendaire' then 100
      when 'rare' then 50
      when 'peu_commun' then 25
      else 10
    end,
    verdict, why, away
  );
  return verdict;
end;
$$;

-- The best players of Paris, or of an arrondissement by the captures made in
-- it, and the player who asks wherever they stand. Accepted captures only.
create function public.leaderboard(in_arrondissement smallint default null, size integer default 50)
returns table (rank bigint, username text, points bigint, captures bigint, is_me boolean)
language sql
stable
security definer
set search_path = ''
as $$
  with scores as (
    select p.id, p.username, sum(c.points) as points, count(*) as captures
    from public.captures c
    join public.profiles p on p.id = c.user_id
    join public.places pl on pl.id = c.monument_id
    where c.status = 'accepted'
      and (in_arrondissement is null or pl.arrondissement = in_arrondissement)
    group by p.id, p.username
  ),
  ranked as (
    select rank() over (order by s.points desc) as rank, s.*
    from scores s
  )
  select r.rank, r.username, r.points, r.captures, r.id = (select auth.uid())
  from ranked r
  where r.rank <= size or r.id = (select auth.uid())
  order by r.rank, r.username;
$$;

revoke execute on function public.submit_capture from public, anon;
grant execute on function public.submit_capture to authenticated;
revoke execute on function public.leaderboard from public, anon;
grant execute on function public.leaderboard to authenticated;
