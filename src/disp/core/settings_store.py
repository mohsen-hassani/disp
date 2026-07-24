import json
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

import structlog
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, Request
from pydantic import TypeAdapter
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core.auth import CurrentUser, current_user, require_admin
from disp.core.contract import SettingsPanelSpec
from disp.core.db import get_session
from disp.core.errors import AppError
from disp.core.models import Setting
from disp.core.registry import Registry

logger = structlog.get_logger(__name__)

SECRET_UNCHANGED_SENTINEL = "***"  # noqa: S105 - masking placeholder, not a credential
# WEB-SPEC §3 amendment A2: this convention key is emitted verbatim into the JSON Schema the
# dashboard manifest serializes (dashboard.py's SettingsPanelOut.schema_), so a JS client can
# detect secret fields directly from the schema as "x-secret": true. Renamed from the old
# internal-only "secret" key now that it's client-visible.
SECRET_FIELD_MARKER = "x-secret"  # noqa: S105 - json_schema_extra convention key, not a credential


class SettingsDecryptionError(Exception):
    pass


class SettingsStore:
    """Encrypted-at-rest key/value store, scoped by (user_id | None, domain, key)."""

    def __init__(self, fernet: Fernet) -> None:
        self._fernet = fernet

    async def get(
        self,
        session: AsyncSession,
        *,
        user_id: UUID | None,
        domain: str,
        key: str,
        default: Any = None,
    ) -> Any:
        row = await self._get_row(session, user_id=user_id, domain=domain, key=key)
        if row is None:
            return default
        return self._decode_value(row)

    async def set(
        self,
        session: AsyncSession,
        *,
        user_id: UUID | None,
        domain: str,
        key: str,
        value: Any,
        is_secret: bool = False,
    ) -> None:
        value_json: Any = None
        value_encrypted: bytes | None = None
        if is_secret:
            plaintext = json.dumps(value).encode("utf-8")
            value_encrypted = self._fernet.encrypt(plaintext)
        else:
            value_json = value

        # updated_at is maintained by application code (§6.1), not a DB trigger.
        now = datetime.now(UTC)
        stmt = (
            pg_insert(Setting)
            .values(
                user_id=user_id,
                module_domain=domain,
                key=key,
                value_json=value_json,
                value_encrypted=value_encrypted,
                is_secret=is_secret,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=[Setting.user_id, Setting.module_domain, Setting.key],
                set_={
                    "value_json": value_json,
                    "value_encrypted": value_encrypted,
                    "is_secret": is_secret,
                    "updated_at": now,
                },
            )
        )
        await session.execute(stmt)

    async def get_all(
        self,
        session: AsyncSession,
        *,
        user_id: UUID | None,
        domain: str,
        reveal_secrets: bool = False,
    ) -> dict[str, Any]:
        rows = await self._get_rows(session, user_id=user_id, domain=domain)
        result: dict[str, Any] = {}
        for row in rows:
            if row.is_secret and not reveal_secrets:
                result[row.key] = SECRET_UNCHANGED_SENTINEL if row.value_encrypted else None
            else:
                result[row.key] = self._decode_value(row)
        return result

    async def delete(
        self, session: AsyncSession, *, user_id: UUID | None, domain: str, key: str
    ) -> None:
        stmt = sa_delete(Setting).where(
            Setting.module_domain == domain,
            Setting.key == key,
            self._user_scope(user_id),
        )
        await session.execute(stmt)

    def _user_scope(self, user_id: UUID | None) -> Any:
        return Setting.user_id == user_id if user_id is not None else Setting.user_id.is_(None)

    async def _get_row(
        self, session: AsyncSession, *, user_id: UUID | None, domain: str, key: str
    ) -> Setting | None:
        stmt = select(Setting).where(
            Setting.module_domain == domain,
            Setting.key == key,
            self._user_scope(user_id),
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_rows(
        self, session: AsyncSession, *, user_id: UUID | None, domain: str
    ) -> list[Setting]:
        stmt = select(Setting).where(
            Setting.module_domain == domain,
            self._user_scope(user_id),
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    def _decode_value(self, row: Setting) -> Any:
        if not row.is_secret:
            return row.value_json
        if row.value_encrypted is None:
            return None
        try:
            plaintext = self._fernet.decrypt(bytes(row.value_encrypted))
        except InvalidToken as exc:
            logger.error("settings_decryption_failed", domain=row.module_domain, key=row.key)
            raise SettingsDecryptionError(
                f"failed to decrypt setting {row.module_domain}.{row.key}"
            ) from exc
        return json.loads(plaintext)


# --------------------------------------------------------------------------
# HTTP router: GET/PUT /api/settings/{domain}
# --------------------------------------------------------------------------

router = APIRouter(tags=["settings"])


def _panel_key_prefix(panel: SettingsPanelSpec) -> str:
    """Return the panel's own namespace within its domain (core.notifier -> notifier)."""
    _, _, suffix = panel.key.partition(".")
    return suffix


def _field_is_secret(field_info: Any) -> bool:
    extra = getattr(field_info, "json_schema_extra", None)
    return isinstance(extra, dict) and bool(extra.get(SECRET_FIELD_MARKER))


def _get_registry(request: Request) -> Registry:
    registry: Registry = request.app.state.registry
    return registry


def _get_store(request: Request) -> SettingsStore:
    return request.app.state.platform.store  # type: ignore[no-any-return]


async def _read_masked_panel(
    session: AsyncSession,
    store: SettingsStore,
    panel: SettingsPanelSpec,
    *,
    domain: str,
    prefix: str,
    target_user_id: UUID | None,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field_name, field_info in panel.schema_model.model_fields.items():
        key = f"{prefix}.{field_name}"
        raw = await store.get(session, user_id=target_user_id, domain=domain, key=key, default=None)
        if _field_is_secret(field_info):
            # Secrets are decrypted server-side only to know what's set; the
            # plaintext must never cross the HTTP boundary (§14.3).
            if isinstance(raw, dict):
                result[field_name] = dict.fromkeys(raw, SECRET_UNCHANGED_SENTINEL)
            else:
                result[field_name] = SECRET_UNCHANGED_SENTINEL if raw is not None else None
        else:
            result[field_name] = raw
    return result


def _find_panel(request: Request, domain: str) -> SettingsPanelSpec:
    registry = _get_registry(request)
    panel = registry.settings_panel_for_domain(domain)
    if panel is None:
        raise AppError(
            status_code=404,
            code="settings.domain_not_found",
            title="Settings domain not found",
            detail=f"No settings panel is registered for domain {domain!r}.",
        )
    return panel


@router.get(
    "/{domain}",
    status_code=200,
    summary="Get the caller's settings for a domain",
    operation_id="settings_get",
    responses={404: {"description": "No settings panel registered for this domain"}},
)
async def get_domain_settings(
    domain: str,
    request: Request,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    panel = _find_panel(request, domain)
    store = _get_store(request)
    prefix = _panel_key_prefix(panel)
    target_user_id = None if panel.scope == "global" else user.id

    return await _read_masked_panel(
        session, store, panel, domain=domain, prefix=prefix, target_user_id=target_user_id
    )


@router.put(
    "/{domain}",
    status_code=200,
    summary="Update the caller's settings for a domain",
    operation_id="settings_update",
    responses={
        403: {"description": "Admin required for a global-scope domain"},
        404: {"description": "No settings panel registered for this domain"},
        422: {"description": "Validation error"},
    },
)
async def update_domain_settings(
    domain: str,
    request: Request,
    payload: dict[str, Any],
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    panel = _find_panel(request, domain)

    if panel.scope == "global":
        await require_admin(user)
        target_user_id = None
    else:
        target_user_id = user.id

    store = _get_store(request)
    prefix = _panel_key_prefix(panel)
    fields = panel.schema_model.model_fields

    unknown = set(payload) - set(fields)
    if unknown:
        raise AppError(
            status_code=422,
            code="validation_error",
            title="Validation error",
            detail=f"Unknown settings field(s): {sorted(unknown)}",
        )

    for field_name, raw_value in payload.items():
        field_info = fields[field_name]
        is_secret = _field_is_secret(field_info)
        key = f"{prefix}.{field_name}"

        if is_secret and raw_value == SECRET_UNCHANGED_SENTINEL:
            continue
        if is_secret and isinstance(raw_value, dict):
            existing = (
                await store.get(session, user_id=target_user_id, domain=domain, key=key, default={})
                or {}
            )
            merged = dict(existing)
            for sub_key, sub_value in raw_value.items():
                if sub_value == SECRET_UNCHANGED_SENTINEL:
                    continue
                merged[sub_key] = sub_value
            await store.set(
                session,
                user_id=target_user_id,
                domain=domain,
                key=key,
                value=merged,
                is_secret=True,
            )
            continue

        adapter: TypeAdapter[Any] = TypeAdapter(field_info.annotation)
        parsed = adapter.validate_python(raw_value)
        # Validating a field like `list[ChannelConfig]` yields model instances;
        # convert back to plain JSON-safe data before it goes into value_json.
        validated = adapter.dump_python(parsed, mode="json")
        await store.set(
            session,
            user_id=target_user_id,
            domain=domain,
            key=key,
            value=validated,
            is_secret=is_secret,
        )

    return await _read_masked_panel(
        session, store, panel, domain=domain, prefix=prefix, target_user_id=target_user_id
    )
