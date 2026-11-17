-- The daily challenge (phase 6): each day, each player has a place to capture
-- that they had not captured before that day, and its capture is worth three
-- times its points. The app and the server draw the same place without
-- talking to each other: the place whose fingerprint, made of the seed of the
-- player, the day in Paris and the identifier of the place, is the smallest.
-- The app keeps the seed from its first start and sends it when the player
-- joins the leaderboards; it cannot change afterwards.

-- Whether the app lets a place be captured: the draw is made among those only.
alter table public.places add column capturable boolean not null default true;

alter table public.profiles add column challenge_seed text;
alter table public.profiles add constraint profiles_challenge_seed_check
  check (challenge_seed ~ '^[0-9a-f]{32}$');

-- A seed set once does not change: a player could otherwise try seeds until
-- the place of the day suits them.
create function public.keep_challenge_seed()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if old.challenge_seed is not null
    and new.challenge_seed is distinct from old.challenge_seed then
    raise exception 'The seed of the daily challenge is set once' using errcode = '42501';
  end if;
  return new;
end;
$$;

create trigger profiles_keep_challenge_seed
  before update on public.profiles
  for each row execute function public.keep_challenge_seed();

alter table public.captures add column daily boolean not null default false;

-- FNV-1a on 32 bits, as apps/mobile/src/features/challenges/daily.ts computes it.
create function public.fnv1a32(input text)
returns bigint
language plpgsql
immutable
strict
set search_path = ''
as $$
declare
  bytes bytea := convert_to(input, 'UTF8');
  hash bigint := 2166136261;
begin
  for i in 0 .. length(bytes) - 1 loop
    hash := ((hash # get_byte(bytes, i)) * 16777619) % 4294967296;
  end loop;
  return hash;
end;
$$;

-- The place of the day of a player: among the places they can capture and had
-- not captured before that day, the one with the smallest fingerprint. None
-- without a seed, or once every place is captured.
create function public.daily_target(player uuid, day date)
returns uuid
language sql
stable
security definer
set search_path = ''
as $$
  select pl.id
  from public.places pl
  join public.profiles p on p.id = player
  where pl.capturable
    and p.challenge_seed is not null
    and not exists (
      select 1 from public.captures c
      where c.user_id = player
        and c.monument_id = pl.id
        and (c.captured_at at time zone 'Europe/Paris')::date < day
    )
  order by public.fnv1a32(p.challenge_seed || ':' || day::text || ':' || pl.id::text), pl.id
  limit 1;
$$;

revoke execute on function public.fnv1a32 from public, anon, authenticated;
revoke execute on function public.daily_target from public, anon, authenticated;
revoke execute on function public.keep_challenge_seed from public, anon, authenticated;

-- The check of a capture, as before, with the daily challenge.
create or replace function public.submit_capture(
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
  -- The capture of the place of the day of the player is worth three times more.
  daily boolean;
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

  -- None without a seed: then no capture is the place of the day.
  daily := coalesce(
    monument = public.daily_target(player, (taken_at at time zone 'Europe/Paris')::date), false
  );

  insert into public.captures (
    id, user_id, monument_id, captured_at, lat, lon, gps_accuracy_m, heading_deg,
    heading_level, geo_score, image_score, chosen_by_player, points, status, reason,
    distance_m, daily
  ) values (
    capture_id, player, monument, taken_at, lat, lon, accuracy_m, heading_deg,
    heading_level, geo_score, image_score, coalesce(chosen_by_player, false),
    -- As the app counts them (apps/mobile/src/features/game/rarity.ts and
    -- apps/mobile/src/features/challenges/daily.ts).
    case place.rarity_tier
      when 'légendaire' then 100
      when 'rare' then 50
      when 'peu_commun' then 25
      else 10
    end * case when daily then 3 else 1 end,
    verdict, why, away, daily
  );
  return verdict;
end;
$$;
