"""Privileged operations are confined to the server, with no secret in responses."""
import requests
from fastapi import HTTPException
from app.config import settings
from app.auth import request_user
from app.core.supabase import identifier


def privileged(method, path, *, body=None, params=None):
    if not settings.supabase_admin_key:
        raise HTTPException(503, 'Gestione amministrativa non configurata sul server (SUPABASE_ADMIN_KEY).')
    try:
        response = requests.request(method, settings.supabase_url.rstrip('/') + path,
            headers={'apikey': settings.supabase_admin_key, 'Authorization': f'Bearer {settings.supabase_admin_key}',
                     'Prefer': 'return=representation'}, json=body, params=params, timeout=20)
    except requests.RequestException as exc:
        raise HTTPException(503, 'Servizio amministrativo non raggiungibile') from exc
    if not response.ok:
        # Never echo upstream payloads, passwords, headers or tokens.
        data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
        if data.get('code') == 'P0001':
            raise HTTPException(429, 'Limite di utilizzo raggiunto. Riprova più tardi o contatta un amministratore.')
        if data.get('code') == '42501':
            raise HTTPException(403, 'Account non abilitato')
        if response.status_code in (400, 409, 422):
            raise HTTPException(422, 'Operazione non accettata: verifica i dati e che l’email non sia già utilizzata.')
        raise HTTPException(502, 'Operazione amministrativa non riuscita')
    return response.json() if response.content else None


def audit(action, target, details=None):
    return privileged('POST', '/rest/v1/admin_audit', body={
        'actor_id': request_user.get().id, 'action': action, 'target': target, 'details': details or {}})


def user_profile(user_id):
    rows = privileged('GET', '/rest/v1/app_profiles', params={'id': f'eq.{identifier(user_id)}'})
    if not rows:
        raise HTTPException(404, 'Utente non trovato')
    return rows[0]
