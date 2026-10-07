-- Apply after 202610070001_chatbot.sql, as database administrator.
begin;
create table public.app_profiles (
 id uuid primary key references auth.users(id) on delete cascade,
 email text not null, display_name text not null default '',
 role text not null default 'user' check(role in ('admin','manager','user')),
 active boolean not null default true,
 must_change_password boolean not null default false,
 session_valid_after timestamptz not null default '1970-01-01',
 monthly_requests integer check(monthly_requests > 0),
 requests_per_minute integer not null default 20 check(requests_per_minute between 1 and 600),
 concurrent_requests integer not null default 2 check(concurrent_requests between 1 and 20),
 created_at timestamptz not null default now()
);
insert into public.app_profiles(id,email,role)
 select id,coalesce(email,''),case when raw_app_meta_data->>'chatbot_role'='admin' then 'admin' else 'user' end from auth.users;
create function public.chatbot_sync_profile() returns trigger language plpgsql security definer set search_path='' as $$
begin
 insert into public.app_profiles(id,email) values(new.id,coalesce(new.email,''))
 on conflict(id) do update set email=excluded.email;
 return new;
end; $$;
create trigger chatbot_profile_sync after insert or update of email on auth.users for each row execute function public.chatbot_sync_profile();
revoke all on function public.chatbot_sync_profile() from public;

create function public.chatbot_role() returns text language sql stable security definer set search_path='' as $$
 select role from public.app_profiles where id=auth.uid() and active and not must_change_password and (auth.jwt()->>'iat')::bigint >= extract(epoch from session_valid_after);
$$;
revoke all on function public.chatbot_role() from public;
grant execute on function public.chatbot_role() to authenticated;

alter table public.knowledge_bases add column shared boolean not null default true;
alter table public.knowledge_bases add column created_by uuid references auth.users(id) on delete set null default auth.uid();
alter table public.documents add column size_bytes bigint not null default 0 check(size_bytes>=0);
create table public.knowledge_members (
 knowledge_id uuid not null references public.knowledge_bases(id) on delete cascade,
 user_id uuid not null references public.app_profiles(id) on delete cascade,
 can_manage boolean not null default false,
 primary key(knowledge_id,user_id)
);
create function public.chatbot_kb_access(kb uuid, manage boolean default false) returns boolean
language sql stable security definer set search_path='' as $$
 select public.chatbot_role()='admin' or (public.chatbot_role() is not null and exists(
 select 1 from public.knowledge_bases k where k.id=kb and (
   (not manage and k.shared) or exists(select 1 from public.knowledge_members m where m.knowledge_id=kb and m.user_id=auth.uid() and (not manage or (m.can_manage and public.chatbot_role()='manager')))
 )));
$$;
revoke all on function public.chatbot_kb_access(uuid,boolean) from public;
grant execute on function public.chatbot_kb_access(uuid,boolean) to authenticated;

create table public.app_models (
 key text primary key, provider text not null check(provider in ('openai','deepseek','ollama')),
 model_id text not null, kind text not null default 'chat' check(kind in ('chat','embedding')), name text not null, enabled boolean not null default true,
 shared boolean not null default true,
 input_per_million numeric check(input_per_million>=0), output_per_million numeric check(output_per_million>=0),
 currency text not null default 'USD' check(currency in ('USD','EUR')),
 unique(provider,model_id), check(key=provider||':'||model_id)
);
insert into public.app_models(key,provider,model_id,name) values
 ('deepseek:deepseek-flash','deepseek','deepseek-flash','DeepSeek Flash'),
 ('deepseek:deepseek-v4-pro','deepseek','deepseek-v4-pro','DeepSeek V4 Pro'),
 ('openai:gpt-4o-mini','openai','gpt-4o-mini','GPT-4o Mini'),
 ('openai:gpt-4o','openai','gpt-4o','GPT-4o'),
 ('ollama:llama3.2','ollama','llama3.2','Llama 3.2');
create table public.model_members (
 model_key text not null references public.app_models(key) on delete cascade,
 user_id uuid not null references public.app_profiles(id) on delete cascade,
 primary key(model_key,user_id)
);
create table public.usage_events (
 id uuid primary key default gen_random_uuid(), parent_id uuid references public.usage_events(id) on delete set null,
 user_id uuid references public.app_profiles(id) on delete set null,
 knowledge_id uuid references public.knowledge_bases(id) on delete set null,
 conversation_id uuid references public.conversations(id) on delete set null,
 operation text not null check(operation in ('request','chat','query_embedding','document_embedding')),
 provider text, model_id text,
 status text not null check(status in ('running','success','error','no_context')),
 input_tokens bigint check(input_tokens>=0), output_tokens bigint check(output_tokens>=0),
 duration_ms bigint check(duration_ms>=0), estimated_cost numeric, currency text,
 input_rate numeric, output_rate numeric,
 error_code text, created_at timestamptz not null default now()
);
create index usage_user_time on public.usage_events(user_id,created_at desc);
create index usage_time on public.usage_events(created_at desc);
create table public.admin_audit (
 id bigint generated always as identity primary key,
 actor_id uuid references public.app_profiles(id) on delete set null,
 action text not null, target text not null, details jsonb not null default '{}',
 created_at timestamptz not null default now()
);

-- RLS policies consult live application permissions, not stale JWT role claims.
alter table public.app_profiles enable row level security;
alter table public.knowledge_members enable row level security;
alter table public.app_models enable row level security;
alter table public.model_members enable row level security;
alter table public.usage_events enable row level security;
alter table public.admin_audit enable row level security;
create policy profiles_read on public.app_profiles for select to authenticated using(id=auth.uid() or public.chatbot_role()='admin');
create policy km_read on public.knowledge_members for select to authenticated using(user_id=auth.uid() or public.chatbot_role()='admin');
create policy models_read on public.app_models for select to authenticated using(public.chatbot_role()='admin' or (public.chatbot_role() is not null and enabled and (shared or exists(select 1 from public.model_members m where m.model_key=key and m.user_id=auth.uid()))));
create policy mm_read on public.model_members for select to authenticated using(user_id=auth.uid() or public.chatbot_role()='admin');
create policy usage_read on public.usage_events for select to authenticated using(public.chatbot_role()='admin' or (public.chatbot_role() is not null and user_id=auth.uid()));
create policy audit_read on public.admin_audit for select to authenticated using(public.chatbot_role()='admin');
grant select on public.app_profiles,public.knowledge_members,public.app_models,public.model_members,public.usage_events,public.admin_audit to authenticated;
revoke all on public.app_profiles,public.knowledge_members,public.app_models,public.model_members,public.usage_events,public.admin_audit from anon;
grant all on public.app_profiles,public.knowledge_members,public.app_models,public.model_members,public.usage_events,public.admin_audit to service_role;
grant usage,select on sequence public.admin_audit_id_seq to service_role;

-- Replace policies from the original migration.
do $$ declare r record; begin
 for r in select tablename,policyname from pg_policies where schemaname='public' and tablename in ('knowledge_bases','documents','conversations','messages') loop
 execute format('drop policy %I on public.%I',r.policyname,r.tablename);
 end loop;
end $$;
create policy knowledge_read on public.knowledge_bases for select to authenticated using(public.chatbot_kb_access(id));
create policy knowledge_insert on public.knowledge_bases for insert to authenticated with check(public.chatbot_role()='admin');
create policy knowledge_update on public.knowledge_bases for update to authenticated using(public.chatbot_role()='admin') with check(public.chatbot_role()='admin');
create policy knowledge_delete on public.knowledge_bases for delete to authenticated using(public.chatbot_role()='admin');
create policy documents_read on public.documents for select to authenticated using(public.chatbot_kb_access(knowledge_id));
create policy documents_write on public.documents for all to authenticated using(public.chatbot_kb_access(knowledge_id,true)) with check(public.chatbot_kb_access(knowledge_id,true));
create policy conversations_owner on public.conversations for all to authenticated
 using(owner_user_id=auth.uid() and public.chatbot_role() is not null)
 with check(owner_user_id=auth.uid() and public.chatbot_role() is not null and (knowledge_id is null or public.chatbot_kb_access(knowledge_id)));
create policy messages_owner on public.messages for all to authenticated
 using(public.chatbot_role() is not null and exists(select 1 from public.conversations c where c.id=conversation_id and c.owner_user_id=auth.uid()))
 with check(public.chatbot_role() is not null and exists(select 1 from public.conversations c where c.id=conversation_id and c.owner_user_id=auth.uid()));

-- All administrative application changes are atomic and audited.
create function public.chatbot_admin_save(kind text, target text, payload jsonb) returns void
language plpgsql security definer set search_path='' as $$
declare member jsonb; actor uuid:=auth.uid(); profile public.app_profiles;
begin
 perform pg_advisory_xact_lock(704210);
 if public.chatbot_role() is distinct from 'admin' then raise exception 'Admin required' using errcode='42501'; end if;
 if kind='profile' then
  select * into strict profile from public.app_profiles where id=target::uuid;
  if profile.role='admin' and profile.active and ((payload->>'role')<>'admin' or not (payload->>'active')::boolean) and
    (select count(*) from public.app_profiles where role='admin' and active and not must_change_password)<=1 then
   raise exception 'Cannot remove last administrator' using errcode='23514';
  end if;
  update public.app_profiles set display_name=payload->>'display_name',role=payload->>'role',active=(payload->>'active')::boolean,
   monthly_requests=(payload->>'monthly_requests')::integer,requests_per_minute=(payload->>'requests_per_minute')::integer,concurrent_requests=(payload->>'concurrent_requests')::integer where id=target::uuid;
 elsif kind='knowledge' then
  update public.knowledge_bases set shared=(payload->>'shared')::boolean where id=target::uuid;
  if not found then raise exception 'Knowledge not found'; end if;
  delete from public.knowledge_members where knowledge_id=target::uuid;
  for member in select * from jsonb_array_elements(payload->'members') loop
   insert into public.knowledge_members values(target::uuid,(member->>'user_id')::uuid,coalesce((member->>'can_manage')::boolean,false));
  end loop;
 elsif kind='force_password' then
  select * into strict profile from public.app_profiles where id=target::uuid;
  if profile.role='admin' and (target::uuid=actor or (select count(*) from public.app_profiles where role='admin' and active and not must_change_password)<=1) then
   raise exception 'Cannot lock last administrator; use own account password change' using errcode='23514';
  end if;
  delete from auth.refresh_tokens where user_id::text=target;
  delete from auth.sessions where user_id=target::uuid;
  update public.app_profiles set must_change_password=true,session_valid_after=date_trunc('second',now())+interval '1 second' where id=target::uuid;
 elsif kind='revoke_sessions' then
  delete from auth.refresh_tokens where user_id::text=target;
  delete from auth.sessions where user_id=target::uuid;
  update public.app_profiles set session_valid_after=date_trunc('second',now())+interval '1 second' where id=target::uuid;
 elsif kind='model' then
  insert into public.app_models(key,provider,model_id,kind,name,enabled,shared,input_per_million,output_per_million,currency)
  values(target,payload->>'provider',payload->>'model_id',coalesce(payload->>'kind','chat'),payload->>'name',(payload->>'enabled')::boolean,(payload->>'shared')::boolean,(payload->>'input_per_million')::numeric,(payload->>'output_per_million')::numeric,coalesce(payload->>'currency','USD'))
  on conflict(key) do update set name=excluded.name,kind=excluded.kind,enabled=excluded.enabled,shared=excluded.shared,input_per_million=excluded.input_per_million,output_per_million=excluded.output_per_million,currency=excluded.currency;
  delete from public.model_members where model_key=target;
  for member in select * from jsonb_array_elements(payload->'members') loop insert into public.model_members values(target,(member->>'user_id')::uuid); end loop;
 else raise exception 'Unknown operation'; end if;
 insert into public.admin_audit(actor_id,action,target,details) values(actor,'save_'||kind,target,payload);
end; $$;
revoke all on function public.chatbot_admin_save(text,text,jsonb) from public;
grant execute on function public.chatbot_admin_save(text,text,jsonb) to authenticated;

-- Request slots and quotas are reserved before any provider call, under a per-user lock.
create function public.chatbot_reserve_request(p_user uuid,p_kb uuid,p_conversation uuid) returns uuid
language plpgsql security definer set search_path='' as $$
declare p public.app_profiles; event uuid;
begin
 select * into strict p from public.app_profiles where id=p_user for update;
 if not p.active or p.must_change_password then raise exception 'Account blocked' using errcode='42501'; end if;
 if p.monthly_requests is not null and (select count(*) from public.usage_events where user_id=p_user and operation='request' and created_at>=date_trunc('month',now() at time zone 'UTC') at time zone 'UTC')>=p.monthly_requests then raise exception 'Monthly request quota reached' using errcode='P0001'; end if;
 if (select count(*) from public.usage_events where user_id=p_user and operation='request' and created_at>now()-interval '1 minute')>=p.requests_per_minute then raise exception 'Rate limit reached' using errcode='P0001'; end if;
 update public.usage_events set status='error',error_code='expired_reservation' where user_id=p_user and operation='request' and status='running' and created_at<=now()-interval '15 minutes';
 -- Each operation has a provider timeout; stale reservations expire after 15 minutes.
 if (select count(*) from public.usage_events where user_id=p_user and operation='request' and status='running' and created_at>now()-interval '15 minutes')>=p.concurrent_requests then raise exception 'Concurrent request limit reached' using errcode='P0001'; end if;
 insert into public.usage_events(user_id,knowledge_id,conversation_id,operation,status) values(p_user,p_kb,p_conversation,'request','running') returning id into event;
 return event;
end; $$;
revoke all on function public.chatbot_reserve_request(uuid,uuid,uuid) from public;
grant execute on function public.chatbot_reserve_request(uuid,uuid,uuid) to service_role;
notify pgrst,'reload schema';
commit;
