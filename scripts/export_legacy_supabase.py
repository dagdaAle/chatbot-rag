"""Offline SQL export. Never contacts Supabase or changes the legacy data."""
import argparse
import json
import sqlite3
from pathlib import Path
from uuid import UUID


def literal(value):
    if value is None:
        return 'NULL'
    if isinstance(value, int):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def insert(table, row):
    return f"insert into public.{table} ({', '.join(row)}) values ({', '.join(literal(v) for v in row.values())}) on conflict do nothing;"


def export(data_dir, owner):
    owner = str(UUID(owner))
    statements = ['begin;']
    kb_file = data_dir / 'knowledges.json'
    kbs = json.loads(kb_file.read_text()).get('knowledges', []) if kb_file.exists() else []
    kb_ids = {str(UUID(k['id'])) for k in kbs}
    for kb in kbs:
        statements.append(insert('knowledge_bases', {k: kb[k] for k in ('id','name','description','created_at')}))
    if (data_dir / 'qdrant').exists():
        from qdrant_client import QdrantClient
        client = QdrantClient(path=str(data_dir / 'qdrant'))
        try:
            names = {c.name for c in client.get_collections().collections}
            for kb_id in kb_ids:
                collection = 'kb_' + kb_id.replace('-', '_')
                if collection not in names:
                    continue
                docs = {}; offset = None
                while True:
                    records, offset = client.scroll(collection, offset=offset, limit=1000, with_vectors=False)
                    for record in records:
                        payload = record.payload or {}
                        if not payload.get('document_id'):
                            continue
                        doc_id = str(UUID(payload['document_id']))
                        row = docs.setdefault(doc_id, {'document_id':doc_id, 'knowledge_id':kb_id,
                            'filename':payload.get('filename','documento.pdf'), 'chunks_count':0,
                            'uploaded_at':payload.get('uploaded_at')})
                        row['chunks_count'] += 1
                    if offset is None:
                        break
                for row in docs.values():
                    if not row['uploaded_at']:
                        del row['uploaded_at']
                    statements.append(insert('documents', row))
        finally:
            client.close()
    db_path = data_dir / 'conversations.db'
    if db_path.exists():
        with sqlite3.connect(f'file:{db_path.resolve()}?mode=ro', uri=True) as db:
            db.row_factory = sqlite3.Row
            for conv in db.execute('select * from conversations'):
                row = {k: conv[k] for k in ('id','title','knowledge_id','created_at','updated_at')}
                row['owner_user_id'] = owner
                if row['knowledge_id'] and row['knowledge_id'] not in kb_ids:
                    row['knowledge_id'] = None
                statements.append(insert('conversations', row))
            for msg in db.execute('select * from messages order by timestamp, id'):
                row = {k:msg[k] for k in ('id','conversation_id','role','content','sources','timestamp')}
                statements.append(insert('messages', row))
    statements.append('commit;')
    return '\n'.join(statements) + '\n'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--owner-user-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = export(args.data_dir, args.owner_user_id)
    # Do not overwrite an existing export; private mode from file creation.
    import os
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(output)
