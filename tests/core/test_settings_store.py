import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core.models import Setting
from disp.core.settings_store import SettingsDecryptionError, SettingsStore
from tests.factories import make_user

# Case 42: secret round-trip encrypts at rest (value_encrypted non-null,
# value_json null) and decrypts correctly.


async def test_secret_round_trip_encrypts_at_rest(db_session: AsyncSession) -> None:
    user = await make_user(db_session, email="settings-secret@example.com")
    store = SettingsStore(Fernet(Fernet.generate_key()))

    await store.set(
        db_session,
        user_id=user.id,
        domain="core",
        key="notifier.urls",
        value={"chan1": "https://example.com/hook"},
        is_secret=True,
    )
    await db_session.flush()

    row = (
        await db_session.execute(
            select(Setting).where(Setting.user_id == user.id, Setting.key == "notifier.urls")
        )
    ).scalar_one()
    assert row.value_encrypted is not None
    assert row.value_json is None

    decoded = await store.get(db_session, user_id=user.id, domain="core", key="notifier.urls")
    assert decoded == {"chan1": "https://example.com/hook"}


# Case 43: get_all masks secrets by default and reveals them only when asked.


async def test_get_all_masks_secrets_by_default(db_session: AsyncSession) -> None:
    user = await make_user(db_session, email="settings-mask@example.com")
    store = SettingsStore(Fernet(Fernet.generate_key()))

    await store.set(
        db_session,
        user_id=user.id,
        domain="core",
        key="notifier.urls",
        value={"a": "b"},
        is_secret=True,
    )
    await store.set(
        db_session, user_id=user.id, domain="core", key="notifier.routing", value={"x": ["a"]}
    )

    masked = await store.get_all(db_session, user_id=user.id, domain="core")
    assert masked["notifier.urls"] == "***"
    assert masked["notifier.routing"] == {"x": ["a"]}

    revealed = await store.get_all(db_session, user_id=user.id, domain="core", reveal_secrets=True)
    assert revealed["notifier.urls"] == {"a": "b"}


# Case 44: a wrong key raises SettingsDecryptionError.


async def test_wrong_key_raises_decryption_error(db_session: AsyncSession) -> None:
    user = await make_user(db_session, email="settings-wrongkey@example.com")
    writer_store = SettingsStore(Fernet(Fernet.generate_key()))
    reader_store = SettingsStore(Fernet(Fernet.generate_key()))

    await writer_store.set(
        db_session,
        user_id=user.id,
        domain="core",
        key="notifier.urls",
        value={"a": "b"},
        is_secret=True,
    )
    await db_session.flush()

    with pytest.raises(SettingsDecryptionError):
        await reader_store.get(db_session, user_id=user.id, domain="core", key="notifier.urls")
