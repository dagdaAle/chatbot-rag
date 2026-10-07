"""Supabase ES256 authentication. No shared secrets or privileged keys."""
from contextvars import ContextVar
from dataclasses import dataclass, replace
from functools import lru_cache
from typing import Any
from uuid import UUID

import jwt
import requests
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.concurrency import run_in_threadpool
from app.config import settings


@dataclass(frozen=True)
class User:
    id: str
    token: str
    is_admin: bool
    app_role: str = "user"
    issued_at: int = 0


request_user: ContextVar[User] = ContextVar('request_user')
bearer = HTTPBearer(auto_error=False)


class _RequestsJWKSClient(jwt.PyJWKClient):
    """PyJWKClient scarica il JWKS con urllib: davanti a Cloudflare quella richiesta
    viene classificata come bot (403, error code 1010) e ogni verifica di token
    finisce in 503. Con requests il fetch passa."""

    def fetch_data(self) -> Any:
        response = requests.get(self.uri, timeout=self.timeout or 10)
        response.raise_for_status()
        return response.json()


@lru_cache(maxsize=1)
def jwks_client():
    return _RequestsJWKSClient(f'{settings.supabase_url.rstrip("/")}/auth/v1/.well-known/jwks.json', cache_keys=False, lifespan=300, timeout=10)


def verify_token(token: str) -> User:
    try:
        key = jwks_client().get_signing_key_from_jwt(token).key
        issuer = settings.supabase_jwt_issuer or f'{settings.supabase_url.rstrip("/")}/auth/v1'
        try:
            claims = jwt.decode(token, key, algorithms=['ES256'], audience='authenticated',
                                issuer=issuer,
                                options={'require': ['exp', 'iat', 'sub', 'iss', 'aud']})
        except jwt.MissingRequiredClaimError:
            # Questa istanza GoTrue self-hosted non emette il claim 'iss'. La firma ES256
            # resta verificata con la chiave pubblica dell'istanza, quindi si accettano i
            # token privi di 'iss' senza allentare le altre verifiche (aud, exp, sub, role).
            claims = jwt.decode(token, key, algorithms=['ES256'], audience='authenticated',
                                options={'require': ['exp', 'iat', 'sub', 'aud']})
        user_id = str(UUID(claims['sub']))
        if claims.get('role') != 'authenticated':
            raise ValueError('Session role required')
        return User(user_id, token, claims.get('app_metadata', {}).get('chatbot_role') == 'admin', issued_at=int(claims['iat']))
    except (jwt.PyJWKClientConnectionError,) as exc:
        raise HTTPException(503, 'Servizio di autenticazione temporaneamente non disponibile') from exc
    except (jwt.PyJWTError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(401, 'Sessione non valida o scaduta', headers={'WWW-Authenticate': 'Bearer'}) from exc


async def current_user(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if not credentials or credentials.scheme.lower() != 'bearer':
        raise HTTPException(401, 'Accedi per continuare', headers={'WWW-Authenticate': 'Bearer'})
    user = await run_in_threadpool(verify_token, credentials.credentials)
    marker = request_user.set(user)
    try:
        from app.core.supabase import rest
        profiles = await run_in_threadpool(rest, 'GET', 'app_profiles', params={'id': f'eq.{user.id}'})
        if not profiles or not profiles[0]['active']:
            raise HTTPException(403, 'Account sospeso o non abilitato')
        profile = profiles[0]
        from datetime import datetime
        if user.issued_at < datetime.fromisoformat(profile['session_valid_after'].replace('Z','+00:00')).timestamp():
            raise HTTPException(401, 'Sessione revocata. Accedi nuovamente.')
        if profile['must_change_password'] and request.url.path not in ('/api/account/me','/api/account/password'):
            raise HTTPException(403, 'Devi cambiare la password prima di continuare')
        user = replace(user, is_admin=profile['role']=='admin', app_role=profile['role'])
        request_user.set(user)
        yield user
    finally:
        request_user.reset(marker)


def require_admin(user: User = Depends(current_user)):
    if not user.is_admin:
        raise HTTPException(403, 'Operazione riservata agli amministratori')
    return user


def require_kb_manager(knowledge_id: str, user: User = Depends(current_user)):
    from app.core.supabase import rest, identifier
    if not rest('POST', 'rpc/chatbot_kb_access', body={'kb': identifier(knowledge_id), 'manage': True}):
        raise HTTPException(403, 'Gestione della knowledge base non consentita')
    return user
