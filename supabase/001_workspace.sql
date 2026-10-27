-- Run once in the dedicated project's SQL editor. No personal data belongs here.
-- Initial migration is additive. History is retained without automatic deletion.
begin;
create table if not exists public.findtrack_workspace (
 owner_id uuid primary key references auth.users(id) on delete cascade,
 revision bigint not null default 1 check(revision>0),
 data jsonb not null check(jsonb_typeof(data)='object'),
 updated_at timestamptz not null default now()
);
create table if not exists public.findtrack_history (
 owner_id uuid not null references auth.users(id) on delete cascade,
 revision bigint not null, data jsonb not null,
 created_at timestamptz not null default now(), primary key(owner_id,revision)
);
alter table public.findtrack_workspace enable row level security;
alter table public.findtrack_history enable row level security;
revoke all on public.findtrack_workspace,public.findtrack_history from anon,public;
grant select,insert,update on public.findtrack_workspace to authenticated;
grant select,insert on public.findtrack_history to authenticated;
create policy owner_workspace on public.findtrack_workspace to authenticated using ((select auth.uid())=owner_id) with check ((select auth.uid())=owner_id);
create policy owner_history on public.findtrack_history to authenticated using ((select auth.uid())=owner_id) with check ((select auth.uid())=owner_id);
create or replace function public.findtrack_load(initial_data jsonb)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare result jsonb;
begin
 if auth.uid() is null then raise insufficient_privilege; end if;
 insert into public.findtrack_workspace(owner_id,data) values(auth.uid(),initial_data) on conflict(owner_id) do nothing;
 select jsonb_build_object('revision',revision,'data',data) into result from public.findtrack_workspace where owner_id=auth.uid();
 return result;
end; $$;
create or replace function public.findtrack_save(expected_revision bigint,new_data jsonb)
returns bigint language plpgsql security invoker set search_path='' as $$
declare previous public.findtrack_workspace; next_revision bigint;
begin
 if auth.uid() is null then raise insufficient_privilege; end if;
 if new_data is null or jsonb_typeof(new_data)<>'object' or octet_length(new_data::text)>5000000 then raise exception using errcode='22023',message='Invalid workspace'; end if;
 select * into previous from public.findtrack_workspace where owner_id=auth.uid() for update;
 if not found or previous.revision<>expected_revision then raise exception using errcode='P0001',message='Workspace revision conflict'; end if;
 insert into public.findtrack_history(owner_id,revision,data) values(auth.uid(),previous.revision,previous.data);
 next_revision=previous.revision+1;
 update public.findtrack_workspace set revision=next_revision,data=new_data,updated_at=now() where owner_id=auth.uid();
 return next_revision;
end; $$;
revoke all on function public.findtrack_load(jsonb),public.findtrack_save(bigint,jsonb) from public,anon;
grant execute on function public.findtrack_load(jsonb),public.findtrack_save(bigint,jsonb) to authenticated;
commit;
