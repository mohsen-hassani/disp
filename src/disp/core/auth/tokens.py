import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TYPE = "access"  # noqa: S105 - JWT `typ` claim value, not a credential

REFRESH_TOKEN_NBYTES = 32
PAT_NBYTES = 32
PAT_PREFIX = "disp_pat_"
# Displayed to the user so they can recognise a token in `disp tokens list`
# without exposing enough of it to be useful for an attacker: the brand
# prefix plus a further 8 characters of the random suffix.
PAT_PREFIX_DISPLAY_LEN = len(PAT_PREFIX) + 8


class InvalidAccessTokenError(Exception):
    pass


class ExpiredAccessTokenError(InvalidAccessTokenError):
    pass


def create_access_token(
    *,
    user_id: uuid.UUID,
    email: str,
    is_admin: bool,
    secret: str,
    ttl_seconds: int,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(seconds=ttl_seconds),
        "jti": str(uuid.uuid4()),
        "typ": ACCESS_TOKEN_TYPE,
        "email": email,
        "adm": is_admin,
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str, *, secret: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[JWT_ALGORITHM],
            leeway=0,
            options={"require": ["exp", "iat", "sub", "typ"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise ExpiredAccessTokenError from exc
    except jwt.PyJWTError as exc:
        raise InvalidAccessTokenError(str(exc)) from exc

    if payload.get("typ") != ACCESS_TOKEN_TYPE:
        raise InvalidAccessTokenError("unexpected token type")
    return dict(payload)


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(REFRESH_TOKEN_NBYTES)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_pat() -> str:
    return PAT_PREFIX + secrets.token_urlsafe(PAT_NBYTES)


def hash_pat(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def pat_prefix(token: str) -> str:
    return token[:PAT_PREFIX_DISPLAY_LEN]


def is_pat(credential: str) -> bool:
    return credential.startswith(PAT_PREFIX)
