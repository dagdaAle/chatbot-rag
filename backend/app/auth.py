"""Supabase ES256 authentication. No shared secrets or privileged keys."""
from contextvars import ContextVar
from dataclasses import dataclass
from functools import lru_cache
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.concurrency import run_in_threadpool
from app.config import settings


@dataclass(frozen=True)
class User:
    id: str
    token: str
    is_admin: bool


request_user: ContextVar[User] = ContextVar('request_user')
bearer = HTTPBearer(auto_error=False)


@lru_cache(maxsize=1)
def jwks_client():
    return jwt.PyJWKClient(f'{settings.supabase_url.rstrip("/")}/auth/v1/.well-known/jwks.json', cache_keys=False, lifespan=300, timeout=10)


def verify_token(token: str) -> User:
    try:
        key = jwks_client().get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=['ES256'], audience='authenticated',
                            issuer=settings.supabase_jwt_issuer or f'{settings.supabase_url.rstrip("/")}/auth/v1',
                            options={'require': ['exp', 'iat', 'sub', 'iss', 'aud']})
        user_id = str(UUID(claims['sub']))
        if claims.get('role') != 'authenticated':
            raise ValueError('Session role required')
        return User(user_id, token, claims.get('app_metadata', {}).get('chatbot_role') == 'admin')
    except (jwt.PyJWKClientConnectionError,) as exc:
        raise HTTPException(503, 'Servizio di autenticazione temporaneamente non disponibile') from exc
    except (jwt.PyJWTError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(401, 'Sessione non valida o scaduta', headers={'WWW-Authenticate': 'Bearer'}) from exc


async def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if not credentials or credentials.scheme.lower() != 'bearer':
        raise HTTPException(401, 'Accedi per continuare', headers={'WWW-Authenticate': 'Bearer'})
    user = await run_in_threadpool(verify_token, credentials.credentials)
    marker = request_user.set(user)
    try:
        yield user
    finally:
        request_user.reset(marker)


def require_admin(user: User = Depends(current_user)):
    if not user.is_admin:
        raise HTTPException(403, 'Operazione riservata agli amministratori')
    return user
