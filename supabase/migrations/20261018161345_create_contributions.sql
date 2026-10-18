-- Photos that players choose to contribute, with what the app knew when it
-- took them (phase 4). Players sign in anonymously: a player reaches only
-- their own rows and photos, to add or delete them; the project reads all of
-- them with its secret key, outside the app.

create table public.contributions (
  -- The identifier of the sample or of the capture on the phone: sending the
  -- same photo twice is refused.
  id uuid primary key,
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  -- A photo of the collect mode, labelled by the player, or of a capture.
  kind text not null,
  taken_at timestamptz not null,
  lat double precision not null,
  lon double precision not null,
  gps_accuracy_m real not null,
  heading_deg real,
  -- How well the compass was calibrated, from 0 to 3: iOS gives no degrees.
  heading_level smallint,
  -- Where the photo is in the bucket "contributions": the folder of the player.
  photo_path text,
  -- The vector that the phone gave the photo.
  vector extensions.vector(384),
  -- Every monument within reach, as the geometry and the photo saw it.
  candidates jsonb not null default '[]'::jsonb,
  -- What the app decided, or would have decided in collect mode.
  decision jsonb,
  -- The monument that the photo shows: the label of a sample, the monument of
  -- a capture; none when the player says it shows no monument of the app. Not
  -- a reference: the places that are not monuments are only in the bundle.
  monument_id uuid,
  chosen_by_player boolean,
  geo_score real,
  image_score real,
  oblique boolean,
  hidden boolean,
  bundle_version text,
  model text,
  app_version text not null,
  -- The text the player agreed to when they turned the contribution on.
  consent_version text not null,
  received_at timestamptz not null default now(),
  constraint contributions_kind_check check (kind in ('sample', 'capture')),
  constraint contributions_heading_level_check check (heading_level between 0 and 3),
  constraint contributions_photo_path_check
    check (photo_path is null or photo_path like user_id::text || '/%')
);

create index contributions_user_id_idx on public.contributions (user_id);

alter table public.contributions enable row level security;

create policy "Players add their own contributions"
  on public.contributions for insert to authenticated
  with check (user_id = (select auth.uid()));

create policy "Players read their own contributions"
  on public.contributions for select to authenticated
  using (user_id = (select auth.uid()));

create policy "Players delete their own contributions"
  on public.contributions for delete to authenticated
  using (user_id = (select auth.uid()));

-- The photos: private, JPEG only, 1 MB at most (a sample weighs about 0.4 MB),
-- each player in a folder named after their identifier.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('contributions', 'contributions', false, 1048576, array['image/jpeg'])
on conflict (id) do nothing;

create policy "Players add photos to their own folder"
  on storage.objects for insert to authenticated
  with check (
    bucket_id = 'contributions'
    and (storage.foldername(name))[1] = (select auth.uid())::text
  );

create policy "Players read the photos of their own folder"
  on storage.objects for select to authenticated
  using (
    bucket_id = 'contributions'
    and (storage.foldername(name))[1] = (select auth.uid())::text
  );

create policy "Players delete the photos of their own folder"
  on storage.objects for delete to authenticated
  using (
    bucket_id = 'contributions'
    and (storage.foldername(name))[1] = (select auth.uid())::text
  );
