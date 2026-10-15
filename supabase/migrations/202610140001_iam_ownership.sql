-- Apply after 202610070002_admin_usage.sql, as database administrator (supabase_admin on self-hosted).
-- IAM rework:
--  * application roles: admin / member / viewer (manager -> member, user -> viewer: nobody gains rights)
--  * knowledge ownership: owner_user_id + visibility private|organization
--  * knowledge_members.role: editor | viewer (can_manage -> editor)
--  * a single SQL source for permissions, exposed to PostgREST as a computed column
--  * conversations/messages re-check knowledge access, deleting a knowledge deletes its chats
begin;

-- 0. Old policies depend on the functions and columns replaced below.
do $$ declare r record; begin
  for r in select tablename, policyname from pg_policies where schemaname = 'public'
    and tablename in ('knowledge_bases','documents','conversations','messages','knowledge_members','import_jobs') loop
    execute format('drop policy %I on public.%I', r.policyname, r.tablename);
  end loop;
end $$;

-- 1. Application roles -------------------------------------------------------
alter table public.app_profiles drop constraint if exists app_profiles_role_check;
update public.app_profiles set role = case role when 'manager' then 'member' when 'user' then 'viewer' else role end;
alter table public.app_profiles alter column role set default 'viewer';
alter table public.app_profiles add constraint app_profiles_role_check check (role in ('admin','member','viewer'));

-- 2. Knowledge ownership and visibility --------------------------------------
alter table public.knowledge_bases add column owner_user_id uuid references public.app_profiles(id);
alter table public.knowledge_bases add column visibility text not null default 'private' check (visibility in ('private','organization'));
update public.knowledge_bases k set
  owner_user_id = coalesce(
    (select p.id from public.app_profiles p where p.id = k.created_by),
    (select p.id from public.app_profiles p where p.role = 'admin' order by p.created_at limit 1)),
  visibility = case when k.shared then 'organization' else 'private' end;
alter table public.knowledge_bases alter column owner_user_id set not null;
alter table public.knowledge_bases alter column owner_user_id set default auth.uid();
alter table public.knowledge_bases drop column shared;
create index knowledge_owner_idx on public.knowledge_bases(owner_user_id);

alter table public.knowledge_members add column role text not null default 'viewer' check (role in ('editor','viewer'));
update public.knowledge_members set role = case when can_manage then 'editor' else 'viewer' end;
alter table public.knowledge_members drop column can_manage;
create index knowledge_members_user_idx on public.knowledge_members(user_id);

-- A deleted knowledge must not turn its chats (and quoted excerpts) into generic chats.
alter table public.conversations drop constraint conversations_knowledge_id_fkey;
alter table public.conversations add constraint conversations_knowledge_id_fkey
  foreign key (knowledge_id) references public.knowledge_bases(id) on delete cascade;

-- 3. Permission functions ----------------------------------------------------
-- Effective permission of the caller on one knowledge: 'owner' | 'editor' | 'viewer' | null.
-- Admins act as owner. The org role 'viewer' caps every assignment at read-only.
create or replace function public.chatbot_kb_permission(kb uuid) returns text
language sql stable security definer set search_path = '' as $$
  with me as (select public.chatbot_role() as role)
  select case
    when me.role is null then null
    when me.role = 'admin' then 'owner'
    when k.owner_user_id = auth.uid() then case when me.role = 'viewer' then 'viewer' else 'owner' end
    when m.role = 'editor' then case when me.role = 'viewer' then 'viewer' else 'editor' end
    when m.role = 'viewer' or k.visibility = 'organization' then 'viewer'
  end
  from me
  join public.knowledge_bases k on k.id = kb
  left join public.knowledge_members m on m.knowledge_id = k.id and m.user_id = auth.uid();
$$;

drop function if exists public.chatbot_kb_access(uuid, boolean);
-- level: 'read' | 'edit' | 'own'
create function public.chatbot_kb_access(kb uuid, level text default 'read') returns boolean
language sql stable security definer set search_path = '' as $$
  select coalesce(case level
    when 'read' then p is not null
    when 'edit' then p in ('owner','editor')
    when 'own'  then p = 'owner'
    else false end, false)
  from (select public.chatbot_kb_permission(kb) as p) s;
$$;

-- PostgREST computed column: GET knowledge_bases?select=*,permission
create function public.permission(public.knowledge_bases) returns text
language sql stable security invoker set search_path = '' as $$
  select public.chatbot_kb_permission($1.id);
$$;

revoke all on function public.chatbot_kb_permission(uuid) from public;
revoke all on function public.chatbot_kb_access(uuid, text) from public;
revoke all on function public.permission(public.knowledge_bases) from public;
grant execute on function public.chatbot_kb_permission(uuid) to authenticated;
grant execute on function public.chatbot_kb_access(uuid, text) to authenticated;
grant execute on function public.permission(public.knowledge_bases) to authenticated;

-- 4. Policies ----------------------------------------------------------------

-- The owner shortcut is needed for INSERT ... RETURNING: the new row is not yet visible
-- to the lookup inside chatbot_kb_permission.
create policy knowledge_read on public.knowledge_bases for select to authenticated
  using ((owner_user_id = (select auth.uid()) and (select public.chatbot_role()) is not null)
         or (select public.chatbot_role()) = 'admin'
         or public.chatbot_kb_access(id, 'read'));
create policy knowledge_insert on public.knowledge_bases for insert to authenticated
  with check (owner_user_id = (select auth.uid()) and (select public.chatbot_role()) in ('admin','member'));
create policy knowledge_update on public.knowledge_bases for update to authenticated
  using (public.chatbot_kb_access(id, 'own')) with check (public.chatbot_kb_access(id, 'own'));
create policy knowledge_delete on public.knowledge_bases for delete to authenticated
  using (public.chatbot_kb_access(id, 'own'));
-- Ownership and visibility change only through chatbot_kb_save (audited, validated).
revoke update on public.knowledge_bases from authenticated;
grant update (name, description) on public.knowledge_bases to authenticated;

create policy documents_read on public.documents for select to authenticated
  using (public.chatbot_kb_access(knowledge_id, 'read'));
create policy documents_write on public.documents for all to authenticated
  using (public.chatbot_kb_access(knowledge_id, 'edit')) with check (public.chatbot_kb_access(knowledge_id, 'edit'));

create policy import_jobs_read on public.import_jobs for select to authenticated
  using (public.chatbot_kb_access(knowledge_id, 'read'));
create policy import_jobs_insert on public.import_jobs for insert to authenticated
  with check (created_by = auth.uid() and public.chatbot_kb_access(knowledge_id, 'edit')
    and status = 'queued' and stage = 'queued' and progress = 0 and attempts = 0 and max_attempts = 3
    and lease_owner is null and lease_expires_at is null
    and extractor is null and extractor_version is null and chunks_count is null
    and last_error_code is null and last_error_message is null
    and started_at is null and completed_at is null);

create or replace function public.chatbot_retry_import_job(p_job uuid)
returns boolean language plpgsql security definer set search_path = '' as $$
declare changed integer;
begin
  update public.import_jobs set status = 'queued', stage = 'queued', progress = 0, attempts = 0,
    lease_owner = null, lease_expires_at = null, last_error_code = null, last_error_message = null,
    started_at = null, completed_at = null, updated_at = clock_timestamp()
  where id = p_job and status = 'failed' and public.chatbot_kb_access(knowledge_id, 'edit');
  get diagnostics changed = row_count;
  return changed = 1;
end; $$;

create policy km_read on public.knowledge_members for select to authenticated
  using (user_id = (select auth.uid()) or public.chatbot_kb_access(knowledge_id, 'own'));

-- Chats stay personal and are readable only while the knowledge is still readable.
create policy conversations_owner on public.conversations for all to authenticated
  using (owner_user_id = (select auth.uid()) and (select public.chatbot_role()) is not null
         and (knowledge_id is null or public.chatbot_kb_access(knowledge_id, 'read')))
  with check (owner_user_id = (select auth.uid()) and (select public.chatbot_role()) is not null
         and (knowledge_id is null or public.chatbot_kb_access(knowledge_id, 'read')));
create policy messages_owner on public.messages for all to authenticated
  using (exists (select 1 from public.conversations c where c.id = conversation_id))
  with check (exists (select 1 from public.conversations c where c.id = conversation_id));
-- (the subquery on conversations is itself filtered by conversations_owner)

-- 5. Sharing: owner or admin, validated and audited ---------------------------
create function public.chatbot_kb_save(kb uuid, payload jsonb) returns void
language plpgsql security definer set search_path = '' as $$
declare member jsonb; new_owner uuid; actor_role text := public.chatbot_role();
begin
  if not public.chatbot_kb_access(kb, 'own') then
    raise exception 'Knowledge sharing not allowed' using errcode = '42501';
  end if;
  new_owner := coalesce((payload->>'owner_user_id')::uuid, (select owner_user_id from public.knowledge_bases where id = kb));
  if new_owner <> (select owner_user_id from public.knowledge_bases where id = kb) then
    if actor_role <> 'admin' then raise exception 'Only admins transfer ownership' using errcode = '42501'; end if;
    if not exists (select 1 from public.app_profiles where id = new_owner and active and role in ('admin','member')) then
      raise exception 'New owner must be an active admin or member' using errcode = '23514';
    end if;
  end if;
  update public.knowledge_bases set
    visibility = coalesce(payload->>'visibility', visibility),
    owner_user_id = new_owner
  where id = kb;
  delete from public.knowledge_members where knowledge_id = kb;
  for member in select * from jsonb_array_elements(coalesce(payload->'members', '[]'::jsonb)) loop
    if (member->>'user_id')::uuid = new_owner then continue; end if;
    if (member->>'role') = 'editor' and exists (select 1 from public.app_profiles where id = (member->>'user_id')::uuid and role = 'viewer') then
      raise exception 'Viewer accounts cannot be editors' using errcode = '23514';
    end if;
    insert into public.knowledge_members(knowledge_id, user_id, role)
      values (kb, (member->>'user_id')::uuid, coalesce(member->>'role', 'viewer'));
  end loop;
  insert into public.admin_audit(actor_id, action, target, details) values (auth.uid(), 'save_knowledge_access', kb::text, payload);
end; $$;
revoke all on function public.chatbot_kb_save(uuid, jsonb) from public;
grant execute on function public.chatbot_kb_save(uuid, jsonb) to authenticated;

-- Minimal directory for the sharing dialog (no quotas, no flags).
create function public.chatbot_directory() returns table(id uuid, email text, display_name text, role text)
language sql stable security definer set search_path = '' as $$
  select p.id, p.email, p.display_name, p.role from public.app_profiles p
  where public.chatbot_role() is not null and p.active order by p.display_name, p.email;
$$;
revoke all on function public.chatbot_directory() from public;
grant execute on function public.chatbot_directory() to authenticated;

-- 6. Admin save: knowledge branch moves to chatbot_kb_save ---------------------
create or replace function public.chatbot_admin_save(kind text, target text, payload jsonb) returns void
language plpgsql security definer set search_path = '' as $$
declare member jsonb; actor uuid := auth.uid(); profile public.app_profiles;
begin
  perform pg_advisory_xact_lock(704210);
  if public.chatbot_role() is distinct from 'admin' then raise exception 'Admin required' using errcode = '42501'; end if;
  if kind = 'profile' then
    select * into strict profile from public.app_profiles where id = target::uuid;
    if profile.role = 'admin' and profile.active and ((payload->>'role') <> 'admin' or not (payload->>'active')::boolean) and
      (select count(*) from public.app_profiles where role = 'admin' and active and not must_change_password) <= 1 then
      raise exception 'Cannot remove last administrator' using errcode = '23514';
    end if;
    update public.app_profiles set display_name = payload->>'display_name', role = payload->>'role', active = (payload->>'active')::boolean,
      monthly_requests = (payload->>'monthly_requests')::integer, requests_per_minute = (payload->>'requests_per_minute')::integer,
      concurrent_requests = (payload->>'concurrent_requests')::integer where id = target::uuid;
    -- A demoted viewer keeps read access only.
    if payload->>'role' = 'viewer' then
      update public.knowledge_members set role = 'viewer' where user_id = target::uuid;
    end if;
  elsif kind in ('force_password', 'revoke_sessions') then
    select * into strict profile from public.app_profiles where id = target::uuid;
    if kind = 'force_password' and profile.role = 'admin' and (target::uuid = actor or
      (select count(*) from public.app_profiles where role = 'admin' and active and not must_change_password) <= 1) then
      raise exception 'Cannot lock last administrator; use own account password change' using errcode = '23514';
    end if;
    delete from auth.refresh_tokens where user_id::text = target;
    delete from auth.sessions where user_id = target::uuid;
    update public.app_profiles set
      must_change_password = must_change_password or kind = 'force_password',
      session_valid_after = date_trunc('second', now()) + interval '1 second'
    where id = target::uuid;
  elsif kind = 'model' then
    insert into public.app_models(key, provider, model_id, kind, name, enabled, shared, input_per_million, output_per_million, currency)
    values (target, payload->>'provider', payload->>'model_id', coalesce(payload->>'kind', 'chat'), payload->>'name', (payload->>'enabled')::boolean,
      (payload->>'shared')::boolean, (payload->>'input_per_million')::numeric, (payload->>'output_per_million')::numeric, coalesce(payload->>'currency', 'USD'))
    on conflict (key) do update set name = excluded.name, kind = excluded.kind, enabled = excluded.enabled, shared = excluded.shared,
      input_per_million = excluded.input_per_million, output_per_million = excluded.output_per_million, currency = excluded.currency;
    delete from public.model_members where model_key = target;
    for member in select * from jsonb_array_elements(payload->'members') loop
      insert into public.model_members values (target, (member->>'user_id')::uuid);
    end loop;
  else raise exception 'Unknown operation'; end if;
  insert into public.admin_audit(actor_id, action, target, details) values (actor, 'save_' || kind, target, payload);
end; $$;

-- The function deletes from auth.sessions/auth.refresh_tokens (owned by supabase_auth_admin).
-- If it is owned by a non-superuser such as postgres, password reset and session revocation
-- fail with "permission denied". Hand it to supabase_admin when that role exists.
do $$ begin
  if exists (select 1 from pg_roles where rolname = 'supabase_admin') then
    execute 'alter function public.chatbot_admin_save(text,text,jsonb) owner to supabase_admin';
  end if;
end $$;

-- 7. Usage aggregates in SQL (RLS applies: admins see all, others their own rows) -------
create function public.chatbot_usage_summary(p_from timestamptz, p_user uuid default null, p_provider text default null, p_model text default null)
returns table(user_id uuid, provider text, model_id text, operation text, calls bigint, errors bigint,
  input_tokens bigint, output_tokens bigint, unknown_tokens bigint, duration_ms bigint, cost numeric, currency text)
language sql stable security invoker set search_path = '' as $$
  select e.user_id, e.provider, e.model_id, e.operation, count(*), count(*) filter (where e.status = 'error'),
    coalesce(sum(e.input_tokens), 0)::bigint, coalesce(sum(e.output_tokens), 0)::bigint,
    count(*) filter (where e.input_tokens is null or e.output_tokens is null),
    coalesce(sum(e.duration_ms), 0)::bigint, sum(e.estimated_cost), max(e.currency)
  from public.usage_events e
  where e.created_at >= p_from and (p_user is null or e.user_id = p_user)
    and (p_provider is null or e.provider = p_provider) and (p_model is null or e.model_id = p_model)
  group by e.user_id, e.provider, e.model_id, e.operation, e.currency;
$$;
revoke all on function public.chatbot_usage_summary(timestamptz, uuid, text, text) from public;
grant execute on function public.chatbot_usage_summary(timestamptz, uuid, text, text) to authenticated;

notify pgrst, 'reload schema';
commit;
