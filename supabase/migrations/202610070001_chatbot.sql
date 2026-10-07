-- Run as database administrator. No service-role key is required by the application.
begin;

create table public.knowledge_bases (
  id uuid primary key default gen_random_uuid(),
  name text not null check (length(btrim(name)) between 1 and 200),
  description text not null default '',
  created_at timestamptz not null default now()
);
create table public.documents (
  document_id uuid primary key default gen_random_uuid(),
  knowledge_id uuid not null references public.knowledge_bases(id) on delete cascade,
  filename text not null,
  chunks_count integer not null check (chunks_count >= 0),
  uploaded_at timestamptz not null default now()
);
create index documents_knowledge_idx on public.documents(knowledge_id);

create table public.conversations (
  id uuid primary key default gen_random_uuid(),
  owner_user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  title text not null check (length(btrim(title)) between 1 and 200),
  knowledge_id uuid references public.knowledge_bases(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index conversations_owner_updated_idx on public.conversations(owner_user_id, updated_at desc);
create table public.messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.conversations(id) on delete cascade,
  role text not null check (role in ('user', 'assistant')),
  content text not null,
  sources jsonb,
  timestamp timestamptz not null default clock_timestamp()
);
create index messages_conversation_time_idx on public.messages(conversation_id, timestamp);

alter table public.knowledge_bases enable row level security;
alter table public.documents enable row level security;
alter table public.conversations enable row level security;
alter table public.messages enable row level security;

create policy knowledge_read on public.knowledge_bases for select to authenticated using (true);
create policy knowledge_admin_insert on public.knowledge_bases for insert to authenticated
  with check ((auth.jwt()->'app_metadata'->>'chatbot_role') = 'admin');
create policy knowledge_admin_update on public.knowledge_bases for update to authenticated
  using ((auth.jwt()->'app_metadata'->>'chatbot_role') = 'admin')
  with check ((auth.jwt()->'app_metadata'->>'chatbot_role') = 'admin');
create policy knowledge_admin_delete on public.knowledge_bases for delete to authenticated
  using ((auth.jwt()->'app_metadata'->>'chatbot_role') = 'admin');

create policy documents_read on public.documents for select to authenticated using (true);
create policy documents_admin_insert on public.documents for insert to authenticated
  with check ((auth.jwt()->'app_metadata'->>'chatbot_role') = 'admin');
create policy documents_admin_update on public.documents for update to authenticated
  using ((auth.jwt()->'app_metadata'->>'chatbot_role') = 'admin')
  with check ((auth.jwt()->'app_metadata'->>'chatbot_role') = 'admin');
create policy documents_admin_delete on public.documents for delete to authenticated
  using ((auth.jwt()->'app_metadata'->>'chatbot_role') = 'admin');

create policy conversations_owner on public.conversations for all to authenticated
  using (owner_user_id = (select auth.uid()))
  with check (owner_user_id = (select auth.uid()));
create policy messages_owner on public.messages for all to authenticated
  using (exists (select 1 from public.conversations c where c.id = conversation_id and c.owner_user_id = (select auth.uid())))
  with check (exists (select 1 from public.conversations c where c.id = conversation_id and c.owner_user_id = (select auth.uid())));

revoke all on public.knowledge_bases, public.documents, public.conversations, public.messages from anon;
grant select, insert, update, delete on public.knowledge_bases, public.documents, public.conversations, public.messages to authenticated;

create function public.chatbot_touch_conversation() returns trigger
language plpgsql security invoker set search_path = '' as $$
begin
  update public.conversations set updated_at = clock_timestamp() where id = new.conversation_id;
  return new;
end;
$$;
create trigger messages_touch_conversation after insert on public.messages
  for each row execute function public.chatbot_touch_conversation();

create function public.save_chat_turn(p_conversation_id uuid, p_question text, p_answer text, p_sources jsonb)
returns void language plpgsql security invoker set search_path = '' as $$
begin
  perform 1 from public.conversations
    where id = p_conversation_id and owner_user_id = auth.uid() for update;
  if not found then
    raise exception 'Conversation not found' using errcode = '42501';
  end if;
  insert into public.messages (conversation_id, role, content)
    values (p_conversation_id, 'user', p_question);
  insert into public.messages (conversation_id, role, content, sources)
    values (p_conversation_id, 'assistant', p_answer, p_sources);
end;
$$;
revoke all on function public.chatbot_touch_conversation() from public;
revoke all on function public.save_chat_turn(uuid,text,text,jsonb) from public;
grant execute on function public.save_chat_turn(uuid,text,text,jsonb) to authenticated;
notify pgrst, 'reload schema';
commit;
