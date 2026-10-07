"""PostgREST using the caller's JWT. RLS remains active for every operation."""
from uuid import UUID
import requests
from fastapi import HTTPException
from app.config import settings
from app.auth import request_user


def identifier(value: str) -> str:
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(422, 'Identificativo non valido') from exc


def rest(method: str, resource: str, *, params=None, body=None):
    user = request_user.get()
    try:
        response = requests.request(method, f'{settings.supabase_url.rstrip("/")}/rest/v1/{resource}',
            headers={'apikey': settings.supabase_publishable_key, 'Authorization': f'Bearer {user.token}',
                     'Prefer': 'return=representation'}, params=params, json=body, timeout=20)
    except requests.RequestException as exc:
        raise HTTPException(503, 'Database temporaneamente non disponibile') from exc
    if not response.ok:
        status = response.status_code if response.status_code in (401, 403, 409) else 502
        raise HTTPException(status, 'Operazione sul database non riuscita')
    return response.json() if response.content else []
