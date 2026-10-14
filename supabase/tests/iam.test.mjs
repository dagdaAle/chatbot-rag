import { PGlite } from '@electric-sql/pglite';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
const db = new PGlite();
await db.exec(`create role anon nologin; create role authenticated nologin; create role service_role nologin bypassrls;
create schema auth;
create table auth.users(id uuid primary key,email text,raw_app_meta_data jsonb default '{}');
create table auth.sessions(id uuid primary key default gen_random_uuid(),user_id uuid references auth.users(id));
create table auth.refresh_tokens(id bigint generated always as identity,user_id text);
create function auth.uid() returns uuid language sql stable as $$ select (nullif(current_setting('request.jwt.claims',true),'')::jsonb->>'sub')::uuid $$;
create function auth.jwt() returns jsonb language sql stable as $$ select nullif(current_setting('request.jwt.claims',true),'')::jsonb $$;
grant usage on schema auth to authenticated,service_role;`);
const migration = name => readFile(new URL(`../migrations/${name}`, import.meta.url), 'utf8');
await db.exec(await migration('202610070001_chatbot.sql'));
const [admin, member, viewer, other] = ['1','2','3','4'].map(n => `00000000-0000-0000-0000-00000000000${n}`);
await db.query(`insert into auth.users(id,email,raw_app_meta_data) values($1,'admin@t.it','{"chatbot_role":"admin"}'),($2,'member@t.it','{}'),($3,'viewer@t.it','{}'),($4,'other@t.it','{}')`, [admin, member, viewer, other]);
await db.exec(await migration('202610070002_admin_usage.sql'));
// Legacy data: one shared KB, one manager with can_manage
await db.query("update public.app_profiles set role='manager' where id in ($1,$2)", [member, other]);
const legacy = (await db.query("insert into public.knowledge_bases(name,created_by) values('Legacy',$1) returning id", [admin])).rows[0].id;
await db.query('insert into public.knowledge_members values($1,$2,true)', [legacy, member]);
await db.exec(await migration('202610140001_iam_ownership.sql'));

const roles = Object.fromEntries((await db.query('select id,role from public.app_profiles')).rows.map(r => [r.id, r.role]));
assert.equal(roles[admin], 'admin'); assert.equal(roles[member], 'member'); assert.equal(roles[viewer], 'viewer');
const kbRow = (await db.query('select owner_user_id,visibility from public.knowledge_bases where id=$1', [legacy])).rows[0];
assert.equal(kbRow.owner_user_id, admin); assert.equal(kbRow.visibility, 'organization');
assert.equal((await db.query('select role from public.knowledge_members where knowledge_id=$1', [legacy])).rows[0].role, 'editor');

async function asUser(id) { await db.exec('reset role'); await db.query("select set_config('request.jwt.claims',$1,false)", [JSON.stringify({ sub: id, iat: Math.floor(Date.now() / 1000) })]); await db.exec('set role authenticated'); }
const perm = async kb => (await db.query('select public.chatbot_kb_permission($1) as p', [kb])).rows[0].p;
const visible = async () => (await db.query('select id from public.knowledge_bases')).rows.map(r => r.id);
const kbSave = (kb, payload) => db.query('select public.chatbot_kb_save($1,$2)', [kb, JSON.stringify(payload)]);

// Member creates a private KB and owns it
await asUser(member);
const mine = (await db.query("insert into public.knowledge_bases(name) values('Papà') returning id, owner_user_id, visibility")).rows[0];
assert.equal(mine.owner_user_id, member); assert.equal(mine.visibility, 'private');
assert.equal(await perm(mine.id), 'owner');
await db.query("insert into public.documents(knowledge_id,filename,chunks_count) values($1,'a.pdf',1)", [mine.id]);
// cannot forge ownership or change it with plain UPDATE
await assert.rejects(db.query("insert into public.knowledge_bases(name,owner_user_id) values('Forged',$1)", [other]));
await assert.rejects(db.query('update public.knowledge_bases set owner_user_id=$1 where id=$2', [other, mine.id]));
const conv = (await db.query("insert into public.conversations(title,knowledge_id) values('c',$1) returning id", [mine.id])).rows[0].id;
await db.query("select public.save_chat_turn($1,'q','a','[]')", [conv]);
// editor on legacy: can upload, cannot share or delete
assert.equal(await perm(legacy), 'editor');
await db.query("insert into public.documents(knowledge_id,filename,chunks_count) values($1,'b.pdf',1)", [legacy]);
await assert.rejects(kbSave(legacy, { visibility: 'private', members: [] }));
assert.equal((await db.query('delete from public.knowledge_bases where id=$1 returning id', [legacy])).rows.length, 0);

// Others do not see a private KB; admins do
await asUser(other); assert.ok(!(await visible()).includes(mine.id)); assert.ok((await visible()).includes(legacy));
await asUser(admin); assert.equal(await perm(mine.id), 'owner');

// Viewer cannot create, cannot be editor, sees only what is shared
await asUser(viewer);
await assert.rejects(db.query("insert into public.knowledge_bases(name) values('No')"));
await asUser(member);
await assert.rejects(kbSave(mine.id, { visibility: 'private', members: [{ user_id: viewer, role: 'editor' }] }));
await kbSave(mine.id, { visibility: 'private', members: [{ user_id: viewer, role: 'viewer' }, { user_id: other, role: 'editor' }] });
await assert.rejects(kbSave(mine.id, { visibility: 'private', members: [], owner_user_id: other }));
await asUser(viewer); assert.equal(await perm(mine.id), 'viewer');
await assert.rejects(db.query("insert into public.documents(knowledge_id,filename,chunks_count) values($1,'x.pdf',1)", [mine.id]));
await asUser(other); assert.equal(await perm(mine.id), 'editor');

// Revocation hides chats on that KB too
await asUser(admin);
await kbSave(mine.id, { visibility: 'private', members: [] });
await asUser(member); assert.equal((await db.query('select * from public.messages')).rows.length, 2);
await asUser(admin); await kbSave(mine.id, { visibility: 'private', members: [], owner_user_id: admin });
await asUser(member);
assert.equal(await perm(mine.id), null);
assert.equal((await db.query('select * from public.conversations')).rows.length, 0);
assert.equal((await db.query('select * from public.messages')).rows.length, 0);

// Deleting a KB deletes its chats instead of turning them into generic chats
await asUser(admin);
await db.query('delete from public.knowledge_bases where id=$1', [mine.id]);
await db.exec('reset role');
assert.equal((await db.query('select count(*)::int as n from public.conversations where id=$1', [conv])).rows[0].n, 0);

// Usage summary runs under RLS
await db.exec('set role service_role');
await db.query("insert into public.usage_events(user_id,operation,status,provider,model_id,input_tokens,output_tokens,estimated_cost,currency) values($1,'chat','success','ollama','m',10,20,0.5,'USD'),($2,'chat','success','ollama','m',1,1,null,null)", [member, other]);
await asUser(member);
const summary = (await db.query("select * from public.chatbot_usage_summary(now()-interval '1 day')")).rows;
assert.equal(summary.length, 1); assert.equal(Number(summary[0].calls), 1);
await asUser(admin);
assert.equal((await db.query("select * from public.chatbot_usage_summary(now()-interval '1 day')")).rows.length, 2);
assert.ok((await db.query('select * from public.chatbot_directory()')).rows.length >= 4);
await db.close(); console.log('IAM passed: role migration, ownership, private by default, editor/viewer, viewer cap, forged owner, revocation hides chats, delete cascade, usage summary.');
