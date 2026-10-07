import { PGlite } from '@electric-sql/pglite';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const db = new PGlite();
await db.exec(`
  create role anon nologin;
  create role authenticated nologin;
  create schema auth;
  create table auth.users (id uuid primary key);
  create function auth.uid() returns uuid language sql stable as $$
    select (nullif(current_setting('request.jwt.claims', true), '')::jsonb->>'sub')::uuid
  $$;
  create function auth.jwt() returns jsonb language sql stable as $$
    select nullif(current_setting('request.jwt.claims', true), '')::jsonb
  $$;
  grant usage on schema auth to authenticated;
`);
await db.exec(await readFile(new URL('../migrations/202610070001_chatbot.sql', import.meta.url), 'utf8'));
const a='00000000-0000-0000-0000-000000000001';
const b='00000000-0000-0000-0000-000000000002';
await db.query('insert into auth.users values ($1),($2)',[a,b]);
async function asUser(id, admin=false, userMetaAdmin=false) {
  await db.exec('reset role');
  await db.query("select set_config('request.jwt.claims', $1, false)", [JSON.stringify({sub:id,role:'authenticated',app_metadata: admin?{chatbot_role:'admin'}:{},user_metadata:userMetaAdmin?{chatbot_role:'admin'}:{}})]);
  await db.exec('set role authenticated');
}
const count=async table => Number((await db.query(`select count(*) from public.${table}`)).rows[0].count);
await asUser(a,true);
const kb=(await db.query("insert into public.knowledge_bases(name) values ('Shared KB') returning id")).rows[0].id;
await db.query("insert into public.documents(knowledge_id,filename,chunks_count) values ($1,'test.pdf',1)",[kb]);
const conv=(await db.query("insert into public.conversations(title, knowledge_id) values ('A personal chat',$1) returning id",[kb])).rows[0].id;
await db.query("select public.save_chat_turn($1,'question','answer','[]'::jsonb)",[conv]);
assert.equal(await count('messages'),2);
await asUser(b);
assert.equal(await count('knowledge_bases'),1);
assert.equal(await count('documents'),1);
assert.equal(await count('conversations'),0);
assert.equal(await count('messages'),0);
await assert.rejects(db.query("insert into public.knowledge_bases(name) values ('Forbidden')"));
await assert.rejects(db.query("insert into public.documents(knowledge_id,filename,chunks_count) values ($1,'forbidden.pdf',1)",[kb]));
await assert.rejects(db.query("insert into public.conversations(owner_user_id,title) values ($1,'Forged owner')",[a]));
await assert.rejects(db.query("insert into public.messages(conversation_id,role,content) values ($1,'user','Forged')",[conv]));
await assert.rejects(db.query("select public.save_chat_turn($1,'forged','forged','[]'::jsonb)",[conv]));
assert.equal((await db.query('delete from public.conversations where id=$1 returning id',[conv])).rows.length,0);
assert.equal((await db.query('update public.conversations set title=\'hijacked\' where id=$1 returning id',[conv])).rows.length,0);
await asUser(b,false,true);
await assert.rejects(db.query("insert into public.knowledge_bases(name) values ('User metadata escalation')"));
await asUser(a,true);
assert.equal(await count('conversations'),1);
assert.equal(await count('messages'),2);
// Ownership cannot be transferred even by an app admin.
await assert.rejects(db.query('update public.conversations set owner_user_id=$1 where id=$2',[b,conv]));
await db.query('delete from public.conversations where id=$1',[conv]);
assert.equal(await count('messages'),0);
await db.exec('reset role; set role anon');
for (const table of ['knowledge_bases','documents','conversations','messages']) {
  await assert.rejects(db.query(`select * from public.${table}`));
}
await assert.rejects(db.query("select public.save_chat_turn($1,'x','x','[]'::jsonb)",[conv]));
await db.close();
console.log('RLS passed: shared read, admin writes, private conversations/messages, forged ownership, RPC, cascade, anon denial.');
