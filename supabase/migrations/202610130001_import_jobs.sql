-- Persistent, recoverable PDF import queue. Apply after 202610070002_admin_usage.sql.
begin;

create table public.import_jobs (
 id uuid primary key default gen_random_uuid(),
 document_id uuid not null unique default gen_random_uuid(),
 knowledge_id uuid not null references public.knowledge_bases(id) on delete cascade,
 created_by uuid references public.app_profiles(id) on delete set null default auth.uid(),
 filename text not null check(length(btrim(filename)) between 1 and 500),
 size_bytes bigint not null check(size_bytes between 1 and 20971520),
 status text not null default 'queued' check(status in ('queued','running','succeeded','failed')),
 stage text not null default 'queued' check(stage in ('queued','extracting','embedding','indexing','publishing','completed','failed')),
 progress integer not null default 0 check(progress between 0 and 100),
 attempts integer not null default 0 check(attempts >= 0),
 max_attempts integer not null default 3 check(max_attempts between 1 and 10),
 lease_owner text,
 lease_expires_at timestamptz,
 extractor text,
 extractor_version text,
 chunks_count integer check(chunks_count >= 0),
 last_error_code text,
 last_error_message text check(last_error_message is null or length(last_error_message) <= 500),
 created_at timestamptz not null default now(),
 started_at timestamptz,
 completed_at timestamptz,
 updated_at timestamptz not null default now(),
 check((status='running') = (lease_owner is not null and lease_expires_at is not null))
);
create index import_jobs_claim_idx on public.import_jobs(status, lease_expires_at, created_at);
create index import_jobs_knowledge_idx on public.import_jobs(knowledge_id, created_at desc);

alter table public.import_jobs enable row level security;
create policy import_jobs_read on public.import_jobs for select to authenticated
 using(public.chatbot_kb_access(knowledge_id));
create policy import_jobs_insert on public.import_jobs for insert to authenticated
 with check(created_by=auth.uid() and public.chatbot_kb_access(knowledge_id,true)
  and status='queued' and stage='queued' and progress=0 and attempts=0 and max_attempts=3
  and lease_owner is null and lease_expires_at is null
  and extractor is null and extractor_version is null and chunks_count is null
  and last_error_code is null and last_error_message is null
  and started_at is null and completed_at is null);

revoke all on public.import_jobs from anon;
grant select on public.import_jobs to authenticated;
-- The caller supplies only upload metadata; the database owns the document ID
-- and all worker state, so a forged insert cannot overwrite another document.
grant insert(id,knowledge_id,filename,size_bytes) on public.import_jobs to authenticated;
grant all on public.import_jobs to service_role;

create function public.chatbot_claim_import_job(p_worker text, p_lease_seconds integer default 600)
returns setof public.import_jobs language plpgsql security definer set search_path='' as $$
declare claimed public.import_jobs;
begin
 if auth.role() <> 'service_role' then raise exception 'Service role required' using errcode='42501'; end if;
 if length(btrim(p_worker)) not between 1 and 200 or p_lease_seconds not between 60 and 1800 then
  raise exception 'Invalid worker lease';
 end if;

 update public.import_jobs set status='failed',stage='failed',progress=100,
  lease_owner=null,lease_expires_at=null,completed_at=clock_timestamp(),updated_at=clock_timestamp(),
  last_error_code='MaxAttemptsExceeded',last_error_message='Importazione interrotta troppe volte.'
 where status='running' and lease_expires_at < clock_timestamp() and attempts >= max_attempts;

 select * into claimed from public.import_jobs
 where (status='queued' or (status='running' and lease_expires_at < clock_timestamp()))
   and attempts < max_attempts
 order by created_at for update skip locked limit 1;
 if not found then return; end if;

 update public.import_jobs set status='running',stage='extracting',progress=5,
  attempts=attempts+1,lease_owner=p_worker,
  lease_expires_at=clock_timestamp()+make_interval(secs=>p_lease_seconds),
  started_at=coalesce(started_at,clock_timestamp()),completed_at=null,
  last_error_code=null,last_error_message=null,updated_at=clock_timestamp()
 where id=claimed.id returning * into claimed;
 return next claimed;
end; $$;

create function public.chatbot_update_import_job(
 p_job uuid,p_worker text,p_status text,p_stage text,p_progress integer,
 p_extractor text default null,p_extractor_version text default null,p_chunks_count integer default null,
 p_error_code text default null,p_error_message text default null,p_lease_seconds integer default 600
) returns boolean language plpgsql security definer set search_path='' as $$
declare changed integer;
begin
 if auth.role() <> 'service_role' then raise exception 'Service role required' using errcode='42501'; end if;
 if p_status not in ('running','succeeded','failed') or
    p_stage not in ('extracting','embedding','indexing','publishing','completed','failed') or
    p_progress not between 0 and 100 or p_lease_seconds not between 60 and 1800 then
  raise exception 'Invalid job state';
 end if;
 update public.import_jobs set status=p_status,stage=p_stage,progress=p_progress,
  lease_owner=case when p_status='running' then p_worker else null end,
  lease_expires_at=case when p_status='running' then clock_timestamp()+make_interval(secs=>p_lease_seconds) else null end,
  extractor=coalesce(p_extractor,extractor),extractor_version=coalesce(p_extractor_version,extractor_version),
  chunks_count=coalesce(p_chunks_count,chunks_count),last_error_code=p_error_code,
  last_error_message=left(p_error_message,500),
  completed_at=case when p_status in ('succeeded','failed') then clock_timestamp() else null end,
  updated_at=clock_timestamp()
 where id=p_job and status='running' and lease_owner=p_worker and lease_expires_at > clock_timestamp();
 get diagnostics changed=row_count;
 return changed=1;
end; $$;

create function public.chatbot_retry_import_job(p_job uuid)
returns boolean language plpgsql security definer set search_path='' as $$
declare changed integer;
begin
 update public.import_jobs set status='queued',stage='queued',progress=0,attempts=0,
  lease_owner=null,lease_expires_at=null,last_error_code=null,last_error_message=null,
  started_at=null,completed_at=null,updated_at=clock_timestamp()
 where id=p_job and status='failed' and public.chatbot_kb_access(knowledge_id,true);
 get diagnostics changed=row_count;
 return changed=1;
end; $$;

revoke all on function public.chatbot_claim_import_job(text,integer) from public;
revoke all on function public.chatbot_update_import_job(uuid,text,text,text,integer,text,text,integer,text,text,integer) from public;
revoke all on function public.chatbot_retry_import_job(uuid) from public;
grant execute on function public.chatbot_claim_import_job(text,integer) to service_role;
grant execute on function public.chatbot_update_import_job(uuid,text,text,text,integer,text,text,integer,text,text,integer) to service_role;
grant execute on function public.chatbot_retry_import_job(uuid) to authenticated;

notify pgrst, 'reload schema';
commit;
