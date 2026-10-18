-- The leaderboards: who reaches what, how a capture is checked, and what the
-- leaderboard shows. Run with `supabase test db`.
begin;
create extension if not exists pgtap with schema extensions;
select plan(27);

-- Three players, signed in anonymously: Nathan, Béa, and one who never joins.
insert into auth.users (id, aud, role, is_anonymous)
values
  ('11111111-1111-4111-8111-111111111111', 'authenticated', 'authenticated', true),
  ('22222222-2222-4222-8222-222222222222', 'authenticated', 'authenticated', true),
  ('33333333-3333-4333-8333-333333333333', 'authenticated', 'authenticated', true);

-- A place: a square of about 110 m around a point, captured from 160 m of it
-- with a GPS accurate to 10 m.
create function pg_temp.place(id uuid, lon double precision, lat double precision,
  tier text, arrondissement smallint)
returns void language sql as $$
  insert into public.places (id, title, location, footprint, arrondissement, rarity_tier, bundle_version)
  values (
    id, 'Lieu', extensions.st_geogfromtext(format('SRID=4326;POINT(%s %s)', lon, lat)),
    extensions.st_geogfromtext(format(
      'SRID=4326;MULTIPOLYGON(((%1$s %2$s, %3$s %2$s, %3$s %4$s, %1$s %4$s, %1$s %2$s)))',
      lon - 0.0005, lat - 0.0005, lon + 0.0005, lat + 0.0005)),
    arrondissement, tier, 'test'
  )
$$;

select pg_temp.place('00000000-0000-4000-8000-000000000001', 2.3499, 48.8530, 'commun', 4::smallint);
select pg_temp.place('00000000-0000-4000-8000-000000000002', 2.3170, 48.8581, 'légendaire', 7::smallint);
select pg_temp.place('00000000-0000-4000-8000-000000000003', 2.3510, 48.8530, 'rare', 4::smallint);
select pg_temp.place('00000000-0000-4000-8000-000000000004', 2.3450, 48.8460, 'commun', 5::smallint);
select pg_temp.place('00000000-0000-4000-8000-000000000005', 2.3499, 48.8980, 'commun', 18::smallint);
select pg_temp.place('00000000-0000-4000-8000-000000000006', 2.3200, 48.8560, 'légendaire', 7::smallint);
-- Thirty places of the 15th, for a day too full.
select pg_temp.place(
  format('00000000-0000-4000-8001-%s', lpad(n::text, 12, '0'))::uuid,
  2.2900 + n * 0.0002, 48.8400, 'commun', 15::smallint)
from generate_series(1, 31) as n;

-- A capture sent by the app.
create function pg_temp.send(place_number integer, taken_at timestamptz,
  lon double precision, lat double precision)
returns text language sql as $$
  select public.submit_capture(
    extensions.gen_random_uuid(),
    format('00000000-0000-4000-8000-%s', lpad(place_number::text, 12, '0'))::uuid,
    taken_at, lat, lon, 10
  )
$$;

create function pg_temp.status(place_number integer)
returns text language sql as $$
  select status || coalesce(' ' || reason, '') from public.captures
  where monument_id = format('00000000-0000-4000-8000-%s', lpad(place_number::text, 12, '0'))::uuid
    and user_id = auth.uid()
$$;

-- Nathan.
set local role authenticated;
set local request.jwt.claims to '{"sub": "11111111-1111-4111-8111-111111111111", "role": "authenticated", "is_anonymous": true}';

select throws_ok(
  $$ select pg_temp.send(1, '2026-10-12 10:00+02', 2.3499, 48.8530) $$,
  '42501', null, 'A player sends no capture before joining'
);
select throws_ok(
  $$ insert into public.profiles (id, username) values ('22222222-2222-4222-8222-222222222222', 'Usurpateur') $$,
  '42501', null, 'A player joins for nobody else'
);
select throws_ok(
  $$ insert into public.profiles (username) values ('ab') $$,
  '23514', null, 'A pseudonym has 3 characters at least'
);
select lives_ok(
  $$ insert into public.profiles (username) values ('Nathan') $$,
  'A player joins under a pseudonym'
);

select is(pg_temp.send(1, '2026-10-12 10:00+02', 2.3499, 48.8530), 'accepted', 'A capture on the spot is accepted');
select is(
  (select points from public.captures where user_id = auth.uid()),
  10, 'It brings the points of the rarity of the place on the server'
);
select is(pg_temp.send(1, '2026-10-12 10:05+02', 2.3499, 48.8530), 'accepted', 'A capture sent twice keeps its verdict');
select is((select count(*)::integer from public.captures), 1, 'and is kept once');

-- 278 m from the outline: farther than 160 m, nearer than twice.
select is(pg_temp.send(2, '2026-10-12 11:00+02', 2.3170, 48.8611), 'pending_review', 'A capture a little far waits for a review');
select is(pg_temp.status(2), 'pending_review far', 'and says why');
select is(pg_temp.send(3, '2026-10-12 11:30+02', 2.3510, 48.8630), 'rejected', 'A capture a kilometre away is refused');
select is(pg_temp.status(3), 'rejected too_far', 'as too far');
select is(
  (select pg_temp.send(4, now() + interval '1 hour', 2.3450, 48.8460)), 'rejected',
  'A capture from the future is refused'
);
-- 5 km two minutes after the first capture.
select is(pg_temp.send(5, '2026-10-12 10:02+02', 2.3499, 48.8980), 'pending_review', 'A capture too fast after the last waits');
select is(pg_temp.status(5), 'pending_review too_fast', 'as too fast');
select is(pg_temp.send(6, '2026-10-12 13:00+02', 2.3200, 48.8560), 'accepted', 'A capture at a walking pace is accepted');
select is(
  (select points from public.captures where monument_id = '00000000-0000-4000-8000-000000000006'),
  100, 'and a legendary place brings 100 points'
);

select throws_ok(
  $$ insert into public.captures (id, user_id, monument_id, captured_at, lat, lon,
       gps_accuracy_m, points, status, distance_m)
     values (extensions.gen_random_uuid(), auth.uid(), '00000000-0000-4000-8000-000000000004',
       now(), 48.846, 2.345, 5, 1000, 'accepted', 0) $$,
  '42501', null, 'A player writes no capture without the check'
);
update public.captures set points = 1000;
select is(
  (select sum(points)::integer from public.captures where status = 'accepted'),
  110, 'nor changes the points of one'
);

-- Béa.
set local request.jwt.claims to '{"sub": "22222222-2222-4222-8222-222222222222", "role": "authenticated", "is_anonymous": true}';

select throws_ok(
  $$ insert into public.profiles (username) values ('NATHAN') $$,
  '23505', null, 'A pseudonym is taken whatever its capitals'
);
insert into public.profiles (username) values ('Béa');
select pg_temp.send(1, '2026-10-12 10:00+02', 2.3499, 48.8530);
select is((select count(*)::integer from public.captures), 1, 'A player sees only their own captures');
select is((select count(*)::integer from public.profiles), 1, 'and only their own profile');

select results_eq(
  $$ select rank, username, points, captures, is_me from public.leaderboard() $$,
  $$ values (1::bigint, 'Nathan'::text, 110::bigint, 2::bigint, false), (2, 'Béa', 10, 1, true) $$,
  'The leaderboard of Paris counts the accepted captures'
);
select results_eq(
  $$ select rank, username, points from public.leaderboard(4::smallint) $$,
  $$ values (1::bigint, 'Béa'::text, 10::bigint), (1, 'Nathan', 10) $$,
  'That of an arrondissement counts the captures made in it'
);
select results_eq(
  $$ select username from public.leaderboard(null, 1) $$,
  $$ values ('Nathan'::text), ('Béa') $$,
  'The player who asks is always in it'
);

-- Béa leaves: her captures go with her profile.
delete from public.profiles;
reset role;
select is(
  (select count(*)::integer from public.captures
   where user_id = '22222222-2222-4222-8222-222222222222'),
  0, 'Leaving the leaderboards deletes the captures'
);

-- Thirty captures in a day for Nathan, then one more.
insert into public.captures (id, user_id, monument_id, captured_at, lat, lon,
  gps_accuracy_m, points, status, distance_m)
select extensions.gen_random_uuid(), '11111111-1111-4111-8111-111111111111',
  format('00000000-0000-4000-8001-%s', lpad(n::text, 12, '0'))::uuid,
  '2026-10-13 09:00+02'::timestamptz + n * interval '1 minute', 48.84, 2.2900 + n * 0.0002,
  5, 10, 'accepted', 0
from generate_series(1, 30) as n;
set local role authenticated;
set local request.jwt.claims to '{"sub": "11111111-1111-4111-8111-111111111111", "role": "authenticated", "is_anonymous": true}';
select is(
  public.submit_capture(extensions.gen_random_uuid(), '00000000-0000-4000-8001-000000000031',
    '2026-10-13 12:00+02', 48.84, 2.2962, 10),
  'pending_review', 'A thirty-first capture in a day waits for a review'
);

select * from finish();
rollback;
