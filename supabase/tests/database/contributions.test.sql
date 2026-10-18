-- The rules of access to the contributions and their photos: run with
-- `supabase test db`.
begin;
create extension if not exists pgtap with schema extensions;
select plan(14);

-- Two players, signed in anonymously.
insert into auth.users (id, aud, role, is_anonymous)
values
  ('11111111-1111-4111-8111-111111111111', 'authenticated', 'authenticated', true),
  ('22222222-2222-4222-8222-222222222222', 'authenticated', 'authenticated', true);

-- A contribution of the first player, as the app sends it.
create function pg_temp.contribute(id uuid, owner uuid default null, photo text default null)
returns void language sql as $$
  insert into public.contributions (
    id, user_id, kind, taken_at, lat, lon, gps_accuracy_m, photo_path,
    app_version, consent_version
  ) values (
    id, coalesce(owner, auth.uid()), 'sample', now(), 48.8462, 2.3443, 5,
    photo, '1.0.0', '2026-10-18'
  )
$$;

set local role authenticated;
set local request.jwt.claims to '{"sub": "11111111-1111-4111-8111-111111111111", "role": "authenticated", "is_anonymous": true}';

select lives_ok(
  $$ select pg_temp.contribute('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', null,
       '11111111-1111-4111-8111-111111111111/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa.jpg') $$,
  'A player adds a contribution'
);
select is(
  (select user_id from public.contributions),
  '11111111-1111-4111-8111-111111111111'::uuid,
  'It belongs to the player'
);
select throws_ok(
  $$ select pg_temp.contribute('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
       '22222222-2222-4222-8222-222222222222') $$,
  '42501', null,
  'A player cannot contribute in the name of another'
);
select throws_ok(
  $$ select pg_temp.contribute('cccccccc-cccc-4ccc-8ccc-cccccccccccc', null,
       '22222222-2222-4222-8222-222222222222/x.jpg') $$,
  '23514', null,
  'A photo is in the folder of its player'
);
select throws_ok(
  $$ select pg_temp.contribute('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa') $$,
  '23505', null,
  'The same photo is not received twice'
);
select lives_ok(
  $$ insert into storage.objects (bucket_id, name)
     values ('contributions', '11111111-1111-4111-8111-111111111111/a.jpg') $$,
  'A player puts a photo in their folder'
);
select throws_ok(
  $$ insert into storage.objects (bucket_id, name)
     values ('contributions', '22222222-2222-4222-8222-222222222222/a.jpg') $$,
  '42501', null,
  'A player cannot put a photo in the folder of another'
);

set local request.jwt.claims to '{"sub": "22222222-2222-4222-8222-222222222222", "role": "authenticated", "is_anonymous": true}';

select is_empty(
  $$ select id from public.contributions $$,
  'A player does not see the contributions of another'
);
select is_empty(
  $$ select name from storage.objects where bucket_id = 'contributions' $$,
  'Nor their photos'
);
delete from public.contributions;

set local request.jwt.claims to '{"sub": "11111111-1111-4111-8111-111111111111", "role": "authenticated", "is_anonymous": true}';

select is(
  (select count(*)::integer from public.contributions), 1,
  'Another player cannot delete them'
);
select lives_ok(
  $$ delete from public.contributions $$,
  'A player deletes their contributions'
);
select is_empty($$ select id from public.contributions $$, 'They are gone');
-- Without a policy for it, a change reaches no row.
select pg_temp.contribute('dddddddd-dddd-4ddd-8ddd-dddddddddddd');
update public.contributions set lat = 0;
select is(
  (select lat from public.contributions), 48.8462::double precision,
  'A contribution is not changed once received'
);

reset role;
set local role anon;
select throws_ok(
  $$ insert into public.contributions (id, user_id, kind, taken_at, lat, lon,
       gps_accuracy_m, app_version, consent_version)
     values ('eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee',
       '11111111-1111-4111-8111-111111111111', 'sample', now(), 0, 0, 5, '1.0.0', 'x') $$,
  '42501', null,
  'Without signing in, nothing is received'
);

select * from finish();
rollback;
