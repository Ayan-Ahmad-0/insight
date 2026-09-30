from dataclasses import dataclass
from uuid import UUID

import jwt
from jwt import PyJWKClient
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings
from .errors import ApiError

bearer = HTTPBearer(auto_error=False)
_jwks = PyJWKClient(f"{settings.issuer}/.well-known/jwks.json",
                    cache_jwk_set=True, lifespan=300)


@dataclass
class Caller:
    user_id: UUID
    org_id: UUID
    claims: dict     # the only claims handed to the database


def _decode(token: str) -> dict:
    opts = dict(audience="authenticated", issuer=settings.issuer,
                options={"require": ["exp", "sub"]})
    try:
        alg = jwt.get_unverified_header(token).get("alg")
        if alg == "HS256" and settings.supabase_jwt_secret:
            return jwt.decode(token, settings.supabase_jwt_secret, algorithms=["HS256"], **opts)
        if alg in ("ES256", "RS256"):
            key = _jwks.get_signing_key_from_jwt(token).key
            return jwt.decode(token, key, algorithms=[alg], **opts)
    except jwt.PyJWTError:
        pass
    raise ApiError(401, "invalid_token", "Token is invalid or expired.")


def get_caller(request: Request,
               creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> Caller:
    if creds is None:
        raise ApiError(401, "missing_token", "Send 'Authorization: Bearer <token>'.")
    claims = _decode(creds.credentials)
    # app_metadata is server-controlled. user_metadata is editable by the user, so never read it.
    raw_org = (claims.get("app_metadata") or {}).get("org_id")
    try:
        org_id = UUID(str(raw_org))
        user_id = UUID(claims["sub"])
    except (ValueError, KeyError):
        raise ApiError(403, "no_organisation", "This account is not linked to an organisation.")
    request.state.org_id = str(org_id)
    return Caller(user_id=user_id, org_id=org_id,
                  claims={"sub": str(user_id), "app_metadata": {"org_id": str(org_id)}})