-- The leaderboard of the week: the same standings, counting only the
-- captures taken since Monday midnight in Paris, so that every week starts
-- afresh for everyone.

-- Monday midnight in Paris of the week of a moment.
create function public.week_start(moment timestamptz)
returns timestamptz
language sql
stable
set search_path = ''
as $$
  select date_trunc('week', moment at time zone 'Europe/Paris') at time zone 'Europe/Paris'
$$;

revoke execute on function public.week_start from public, anon, authenticated;

-- The leaderboard asks now whether to count all the captures or those of the
-- week; the apps that do not ask get the leaderboard of all time.
drop function public.leaderboard(smallint, integer);

-- The best players of Paris, or of an arrondissement by the captures made in
-- it, of all time or of the week, and the player who asks wherever they
-- stand. Accepted captures only.
create function public.leaderboard(
  in_arrondissement smallint default null,
  size integer default 50,
  weekly boolean default false
)
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
      and (not weekly or c.captured_at >= public.week_start(now()))
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

revoke execute on function public.leaderboard from public, anon;
grant execute on function public.leaderboard to authenticated;
