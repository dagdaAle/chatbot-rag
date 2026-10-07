"""Shared knowledge metadata in Supabase; embeddings stay in Qdrant."""
from dataclasses import dataclass
from uuid import uuid4
from app.core.supabase import rest, identifier
from app.core.qdrant_client import get_client, ensure_collection_for_kb, delete_collection_for_kb
from app.core.documents import delete_knowledge_pdfs


@dataclass
class Knowledge:
    id: str
    name: str
    description: str
    created_at: str
    documents_count: int = 0
    can_manage: bool = False


def get_collection_name(knowledge_id):
    return 'kb_' + identifier(knowledge_id).replace('-', '_')


def _knowledge(row):
    from app.auth import request_user
    try:
        user = request_user.get()
        can_manage = user.is_admin or (user.app_role == 'manager' and any(m['user_id']==user.id and m['can_manage'] for m in row.get('knowledge_members', [])))
    except LookupError:
        can_manage = False
    return Knowledge(id=row['id'], name=row['name'], description=row.get('description', ''),
                     created_at=row['created_at'], documents_count=row.get('documents', [{}])[0].get('count', 0), can_manage=can_manage)


def list_knowledges():
    return [_knowledge(row) for row in rest('GET', 'knowledge_bases', params={'select':'*,documents(count),knowledge_members(user_id,can_manage)', 'order':'created_at.asc'})]


def get_knowledge(knowledge_id):
    rows = rest('GET', 'knowledge_bases', params={'id':f'eq.{identifier(knowledge_id)}', 'select':'*,documents(count),knowledge_members(user_id,can_manage)'})
    return _knowledge(rows[0]) if rows else None


def create_knowledge(name, description=''):
    kb_id = str(uuid4())
    row = rest('POST', 'knowledge_bases', body={'id':kb_id, 'name':name, 'description':description})[0]
    try:
        ensure_collection_for_kb(get_client(), get_collection_name(kb_id))
    except Exception:
        rest('DELETE', 'knowledge_bases', params={'id':f'eq.{kb_id}'})
        raise
    return _knowledge(row)


def delete_knowledge(knowledge_id):
    if not get_knowledge(knowledge_id):
        return False
    # Do not swallow vector-storage errors or remove metadata before cleanup succeeds.
    client = get_client()
    name = get_collection_name(knowledge_id)
    if any(c.name == name for c in client.get_collections().collections):
        client.delete_collection(name)
    delete_knowledge_pdfs(knowledge_id)
    return bool(rest('DELETE', 'knowledge_bases', params={'id':f'eq.{identifier(knowledge_id)}'}))


def update_documents_count(*args, **kwargs):
    # Derived from document rows; never updated by GET requests.
    pass
