-- The leaderboard of the week: when a week starts in Paris, and which captures
-- it counts. Run with `supabase test db`.
begin;
create extension if not exists pgtap with schema extensions;
select plan(11);

-- When the week starts.
select is(public.week_start('2026-11-18 00:30+01'), '2026-11-16 00:00+01'::timestamptz,
  'A week starts on Monday at midnight in Paris');
select is(public.week_start('2026-11-16 00:00+01'), '2026-11-16 00:00+01'::timestamptz,
  'Monday at midnight is the first moment of the week');
select is(public.week_start('2026-11-15 23:59+01'), '2026-11-09 00:00+01'::timestamptz,
  'Sunday night is still the week before');
select is(public.week_start('2026-11-15 23:30Z'), '2026-11-16 00:00+01'::timestamptz,
  'The week turns in Paris, not in UTC');
select is(public.week_start('2026-03-31 10:00+02'), '2026-03-30 00:00+02'::timestamptz,
  'in summer time too');
select is(public.week_start('2026-03-29 12:00+02'), '2026-03-23 00:00+01'::timestamptz,
  'and on the Sunday the clocks change');

-- Two players and their captures, written directly: the leaderboard alone is
-- under test.
truncate public.captures, public.profiles;
insert into auth.users (id, aud, role, is_anonymous)
values
  ('11111111-1111-4111-8111-111111111111', 'authenticated', 'authenticated', true),
  ('22222222-2222-4222-8222-222222222222', 'authenticated', 'authenticated', true);
insert into public.profiles (id, username)
values
  ('11111111-1111-4111-8111-111111111111', 'Nathan'),
  ('22222222-2222-4222-8222-222222222222', 'Béa');

create function pg_temp.place(n integer, arrondissement smallint)
returns void language sql as $$
  insert into public.places (id, title, location, footprint, arrondissement, rarity_tier, bundle_version)
  values (
    format('00000000-0000-4000-8000-%s', lpad(n::text, 12, '0'))::uuid, 'Lieu',
    extensions.st_geogfromtext('SRID=4326;POINT(2.35 48.85)'),
    extensions.st_geogfromtext(
      'SRID=4326;MULTIPOLYGON(((2.3495 48.8495, 2.3505 48.8495, 2.3505 48.8505, 2.3495 48.8505, 2.3495 48.8495)))'),
    arrondissement, 'commun', 'test'
  )
$$;

select pg_temp.place(1, 4::smallint);
select pg_temp.place(2, 4::smallint);
select pg_temp.place(3, 7::smallint);
select pg_temp.place(4, 7::smallint);

create function pg_temp.capture(player uuid, n integer, taken_at timestamptz, points integer, status text)
returns void language sql as $$
  insert into public.captures (id, user_id, monument_id, captured_at, lat, lon,
    gps_accuracy_m, points, status, distance_m)
  values (extensions.gen_random_uuid(), player,
    format('00000000-0000-4000-8000-%s', lpad(n::text, 12, '0'))::uuid,
    taken_at, 48.85, 2.35, 5, points, status, 0)
$$;

-- Nathan: a capture just before the week, one at its very start.
select pg_temp.capture('11111111-1111-4111-8111-111111111111', 3,
  public.week_start(now()) - interval '1 second', 100, 'accepted');
select pg_temp.capture('11111111-1111-4111-8111-111111111111', 1,
  public.week_start(now()), 10, 'accepted');
-- Béa: a capture of the week, and one that waits for a review.
select pg_temp.capture('22222222-2222-4222-8222-222222222222', 2,
  public.week_start(now()), 50, 'accepted');
select pg_temp.capture('22222222-2222-4222-8222-222222222222', 4,
  public.week_start(now()), 30, 'pending_review');

-- Nathan asks.
set local role authenticated;
set local request.jwt.claims to '{"sub": "11111111-1111-4111-8111-111111111111", "role": "authenticated", "is_anonymous": true}';

select results_eq(
  $$ select rank, username, points, captures, is_me from public.leaderboard(null, 50, true) $$,
  $$ values (1::bigint, 'Béa'::text, 50::bigint, 1::bigint, false), (2, 'Nathan', 10, 1, true) $$,
  'The leaderboard of the week counts the accepted captures since Monday midnight'
);
select results_eq(
  $$ select rank, username, points, captures, is_me from public.leaderboard() $$,
  $$ values (1::bigint, 'Nathan'::text, 110::bigint, 2::bigint, true), (2, 'Béa', 50, 1, false) $$,
  'That of all time counts them all'
);
select is_empty(
  $$ select * from public.leaderboard(7::smallint, 50, true) $$,
  'An arrondissement without an accepted capture this week has nobody yet'
);
select results_eq(
  $$ select username from public.leaderboard(null, 1, true) $$,
  $$ values ('Béa'::text), ('Nathan') $$,
  'The player who asks is in the leaderboard of the week wherever they stand'
);
select throws_ok(
  $$ select public.week_start(now()) $$,
  '42501', null, 'A player calls no helper of the leaderboard'
);

select * from finish();
rollback;
