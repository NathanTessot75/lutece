-- The daily challenge: the fingerprint, the draw of the place of the day, the
-- seed of a player, and the points of a capture of the place of the day. The
-- expected places are those that apps/mobile/src/features/challenges/daily.ts
-- draws from the same seed (see daily.test.ts). Run with `supabase test db`.
begin;
create extension if not exists pgtap with schema extensions;
select plan(18);

insert into auth.users (id, aud, role, is_anonymous)
values
  ('11111111-1111-4111-8111-111111111111', 'authenticated', 'authenticated', true),
  ('22222222-2222-4222-8222-222222222222', 'authenticated', 'authenticated', true);

-- Only the places of the test take part in the draw.
truncate public.places cascade;

-- A place: a square of about 110 m around a point.
create function pg_temp.place(id uuid, lon double precision, lat double precision, tier text)
returns void language sql as $$
  insert into public.places (id, title, location, footprint, arrondissement, rarity_tier, bundle_version)
  values (
    id, 'Lieu', extensions.st_geogfromtext(format('SRID=4326;POINT(%s %s)', lon, lat)),
    extensions.st_geogfromtext(format(
      'SRID=4326;MULTIPOLYGON(((%1$s %2$s, %3$s %2$s, %3$s %4$s, %1$s %4$s, %1$s %2$s)))',
      lon - 0.0005, lat - 0.0005, lon + 0.0005, lat + 0.0005)),
    4, tier, 'test'
  )
$$;

select pg_temp.place('00000000-0000-4000-8000-000000000001', 2.3499, 48.8530, 'commun');
select pg_temp.place('00000000-0000-4000-8000-000000000002', 2.3510, 48.8540, 'commun');
select pg_temp.place('00000000-0000-4000-8000-000000000003', 2.3520, 48.8550, 'commun');
select pg_temp.place('00000000-0000-4000-8000-000000000004', 2.3530, 48.8560, 'rare');

create function pg_temp.place_id(n integer)
returns uuid language sql as $$
  select format('00000000-0000-4000-8000-%s', lpad(n::text, 12, '0'))::uuid
$$;

create function pg_temp.target(player uuid, day date)
returns uuid language sql as $$ select public.daily_target(player, day) $$;

select is(public.fnv1a32(''), 2166136261::bigint, 'The fingerprint of nothing is the offset of FNV-1a');
select is(public.fnv1a32('foobar'), 3214735720::bigint, 'The fingerprint of « foobar » is that of FNV-1a');
select is(public.fnv1a32('é'), 513665217::bigint, 'The fingerprint reads the bytes of UTF-8');

-- Nathan has a seed; Béa joined before the daily challenge.
insert into public.profiles (id, username, challenge_seed)
values
  ('11111111-1111-4111-8111-111111111111', 'Nathan', '0123456789abcdef0123456789abcdef'),
  ('22222222-2222-4222-8222-222222222222', 'Béa', null);

select is(
  pg_temp.target('11111111-1111-4111-8111-111111111111', '2026-11-10'), pg_temp.place_id(4),
  'The place of the day is the one with the smallest fingerprint'
);
select is(
  pg_temp.target('11111111-1111-4111-8111-111111111111', '2026-11-11'), pg_temp.place_id(3),
  'Another day draws another place'
);
select is(
  pg_temp.target('22222222-2222-4222-8222-222222222222', '2026-11-10'), null,
  'Without a seed, a player has no place of the day'
);
update public.places set capturable = false where id = pg_temp.place_id(4);
select is(
  pg_temp.target('11111111-1111-4111-8111-111111111111', '2026-11-10'), pg_temp.place_id(1),
  'A place that cannot be captured is never drawn'
);
update public.places set capturable = true where id = pg_temp.place_id(4);

select throws_ok(
  $$ update public.profiles set challenge_seed = 'xyz' where username = 'Béa' $$,
  '23514', null, 'A seed is 32 hexadecimal digits'
);
select lives_ok(
  $$ update public.profiles set challenge_seed = 'fedcba9876543210fedcba9876543210' where username = 'Béa' $$,
  'A player without a seed receives one'
);
select throws_ok(
  $$ update public.profiles set challenge_seed = '00000000000000000000000000000000' where username = 'Béa' $$,
  '42501', null, 'A seed set once does not change'
);
select lives_ok(
  $$ update public.profiles set challenge_seed = 'fedcba9876543210fedcba9876543210', username = 'Béatrice'
     where username = 'Béa' $$,
  'A player who sends their seed again changes nothing'
);

-- Nathan captures the place of the 10th, then another place the same day.
set local role authenticated;
set local request.jwt.claims to '{"sub": "11111111-1111-4111-8111-111111111111", "role": "authenticated", "is_anonymous": true}';

select is(
  public.submit_capture(extensions.gen_random_uuid(), pg_temp.place_id(4), '2026-11-10 10:00+01', 48.8560, 2.3530, 10),
  'accepted', 'The place of the day is captured'
);
select is(
  public.submit_capture(extensions.gen_random_uuid(), pg_temp.place_id(1), '2026-11-10 12:00+01', 48.8530, 2.3499, 10),
  'accepted', 'Another place is captured the same day'
);
select results_eq(
  $$ select points, daily from public.captures order by captured_at $$,
  $$ values (150, true), (10, false) $$,
  'The place of the day is worth three times its points, the others their own'
);

reset role;
select is(
  pg_temp.target('11111111-1111-4111-8111-111111111111', '2026-11-10'), pg_temp.place_id(4),
  'A capture of the day leaves the place of the day as it was'
);
select is(
  pg_temp.target('11111111-1111-4111-8111-111111111111', '2026-11-15'), pg_temp.place_id(3),
  'A place captured before the day is not drawn'
);
select is(
  pg_temp.target('11111111-1111-4111-8111-111111111111', '2026-11-16'), pg_temp.place_id(2),
  'Nor any of those captured before'
);
select is(
  (select count(*) from public.captures where daily)::integer, 1,
  'One place of the day was captured'
);

select * from finish();
rollback;
