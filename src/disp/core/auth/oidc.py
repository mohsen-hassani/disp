from sqlalchemy.ext.asyncio import AsyncSession

from disp.core.auth.dependencies import CurrentUser


async def resolve_external_token(token: str, session: AsyncSession) -> CurrentUser:
    """Reserved for a future external OIDC provider.

    Planned implementation:
      1. Fetch and cache the issuer's JWKS from OIDC discovery.
      2. Validate signature, `iss`, `aud`, and `exp`.
      3. Look up core.users by (external_issuer, external_subject).
      4. If absent, link by verified email on first login; otherwise 403.

    Wiring point: a fourth branch in `dependencies.current_user`, taken when
    the JWT's `iss` claim is not this application. No other file changes.
    """
    raise NotImplementedError("External OIDC is not enabled in this deployment.")
