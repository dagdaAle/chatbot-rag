"""Personal conversations in Supabase; caller JWT and owner filters enforce scope."""
from uuid import uuid4
from fastapi import HTTPException
from app.auth import request_user
from app.core.supabase import rest, identifier


def scope(conversation_id=None):
    filters = {'owner_user_id': f'eq.{request_user.get().id}'}
    if conversation_id is not None:
        filters['id'] = f'eq.{identifier(conversation_id)}'
    return filters


def list_conversations(limit=100):
    return rest('GET', 'conversations', params={**scope(), 'order': 'updated_at.desc', 'limit': limit})


def get_conversation(conversation_id):
    rows = rest('GET', 'conversations', params={**scope(conversation_id), 'select': '*,messages(*)'})
    if not rows:
        return None
    conv = rows[0]
    conv['messages'] = sorted(conv.get('messages', []), key=lambda m: (m['timestamp'], m['id']))
    return conv


def create_conversation(title, knowledge_id=None):
    return rest('POST', 'conversations', body={'id': str(uuid4()), 'title': title,
        'owner_user_id': request_user.get().id,
        'knowledge_id': identifier(knowledge_id) if knowledge_id else None})[0]


def delete_conversation(conversation_id):
    return bool(rest('DELETE', 'conversations', params=scope(conversation_id)))


def add_message(conversation_id, role, content, sources=None):
    if not get_conversation(conversation_id):
        raise ValueError('Conversazione non trovata')
    return rest('POST', 'messages', body={'conversation_id': identifier(conversation_id),
        'role': role, 'content': content, 'sources': sources})[0]


def save_turn(conversation_id, question, answer, sources):
    rest('POST', 'rpc/save_chat_turn', body={'p_conversation_id': identifier(conversation_id),
        'p_question': question, 'p_answer': answer, 'p_sources': sources})


def update_conversation_title(conversation_id, title):
    return bool(rest('PATCH', 'conversations', params=scope(conversation_id), body={'title': title}))
