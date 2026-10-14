"""Knowledge metadata in Supabase; embeddings stay in Qdrant.

Permissions are computed by SQL (`permission` computed column) and only echoed here."""
import logging
from dataclasses import dataclass
from uuid import uuid4
from app.core.supabase import rest, identifier
from app.core.qdrant_client import get_client, ensure_collection_for_kb
from app.core.documents import delete_knowledge_pdfs

logger = logging.getLogger(__name__)
SELECT = '*,permission,documents(count)'


@dataclass
class Knowledge:
    id: str
    name: str
    description: str
    created_at: str
    owner_user_id: str
    visibility: str
    permission: str | None
    documents_count: int = 0

    @property
    def can_edit(self) -> bool:
        return self.permission in ('owner', 'editor')

    @property
    def can_own(self) -> bool:
        return self.permission == 'owner'


def get_collection_name(knowledge_id):
    return 'kb_' + identifier(knowledge_id).replace('-', '_')


def _knowledge(row):
    return Knowledge(id=row['id'], name=row['name'], description=row.get('description', ''),
                     created_at=row['created_at'], owner_user_id=row['owner_user_id'],
                     visibility=row['visibility'], permission=row.get('permission'),
                     documents_count=(row.get('documents') or [{}])[0].get('count', 0))


def list_knowledges():
    return [_knowledge(r) for r in rest('GET', 'knowledge_bases', params={'select': SELECT, 'order': 'created_at.asc'})]


def get_knowledge(knowledge_id):
    rows = rest('GET', 'knowledge_bases', params={'id': f'eq.{identifier(knowledge_id)}', 'select': SELECT})
    return _knowledge(rows[0]) if rows else None


def create_knowledge(name, description='', visibility='private'):
    kb_id = str(uuid4())
    from app.auth import request_user
    rest('POST', 'knowledge_bases', body={'id': kb_id, 'name': name, 'description': description,
                                          'visibility': visibility, 'owner_user_id': request_user.get().id})
    try:
        ensure_collection_for_kb(get_client(), get_collection_name(kb_id))
    except Exception:
        rest('DELETE', 'knowledge_bases', params={'id': f'eq.{kb_id}'})
        raise
    return get_knowledge(kb_id)


def update_knowledge(knowledge_id, name, description):
    rest('PATCH', 'knowledge_bases', params={'id': f'eq.{identifier(knowledge_id)}'},
         body={'name': name, 'description': description})
    return get_knowledge(knowledge_id)


def save_access(knowledge_id, visibility, members, owner_user_id=None):
    payload = {'visibility': visibility, 'members': members}
    if owner_user_id:
        payload['owner_user_id'] = owner_user_id
    rest('POST', 'rpc/chatbot_kb_save', body={'kb': identifier(knowledge_id), 'payload': payload})


def list_members(knowledge_id):
    return rest('GET', 'knowledge_members', params={'knowledge_id': f'eq.{identifier(knowledge_id)}', 'select': 'user_id,role'})


def delete_knowledge(knowledge_id):
    """Metadata first (RLS checks ownership, chats and documents cascade), then storage.
    A storage failure leaves only orphan vectors/files, never a visible half-deleted knowledge."""
    if not rest('DELETE', 'knowledge_bases', params={'id': f'eq.{identifier(knowledge_id)}'}):
        return False
    try:
        client = get_client()
        name = get_collection_name(knowledge_id)
        if any(c.name == name for c in client.get_collections().collections):
            client.delete_collection(name)
        delete_knowledge_pdfs(knowledge_id)
    except Exception:
        logger.exception('Orphan storage left for deleted knowledge %s', knowledge_id)
    return True
