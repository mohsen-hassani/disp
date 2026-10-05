"""TranslationFacade's sync surface, and the sync session primitive it needed
(M22-translation.md §5.1, §7.1).

The fixtures below are the sync mirror of the root conftest's
`db_connection`/`session_maker` pair: a real psycopg connection, one outer
transaction per test, sessions joined to it via SAVEPOINTs, rolled back
afterwards. Without that, `sync_session_scope`'s real COMMIT would leak rows
past the per-test boundary and every count assertion in this directory would
depend on run order.

T3 (no event loop in the package) is pinned by a grep in
tests/core/test_boundaries.py rather than here — it is a property of the
source tree, not of a call.
"""

import os
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session, sessionmaker

from disp.core.config import Settings, get_settings
from disp.core.db import create_sync_engine
from disp.core.models import TranslationCallRow
from disp.core.translation import (
    FakeTranslationBackend,
    TranslationFacade,
    TranslationInputTooLarge,
    TranslationNotConfigured,
    TranslationUnavailable,
)
from disp.core.translation.usage import CallRecord, write_call_sync


@pytest.fixture
def sync_connection() -> Iterator[Connection]:
    engine = create_sync_engine(os.environ["DISP_DATABASE_URL_SYNC"])
    with engine.connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()
    engine.dispose()


@pytest.fixture
def sync_session_maker(sync_connection: Connection) -> sessionmaker[Session]:
    return sessionmaker(
        bind=sync_connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )


def _settings(**overrides: object) -> Settings:
    data = get_settings().model_dump()
    data.update(translation_enabled=True, translation_backend="fake")
    data.update(overrides)
    return Settings(**data)


def _facade(
    sync_session_maker: sessionmaker[Session],
    backend: FakeTranslationBackend | None = None,
    **overrides: object,
) -> TranslationFacade:
    return TranslationFacade(
        _settings(**overrides),
        None,
        sync_session_maker,
        backend=backend if backend is not None else FakeTranslationBackend(),
    )


def _rows(session_maker: sessionmaker[Session]) -> list[TranslationCallRow]:
    with session_maker() as session:
        return list(session.execute(select(TranslationCallRow)).scalars())


def _row_count(session_maker: sessionmaker[Session]) -> int:
    with session_maker() as session:
        return session.execute(select(func.count()).select_from(TranslationCallRow)).scalar_one()


def test_translate_sync_returns_results_in_order(
    sync_session_maker: sessionmaker[Session],
) -> None:
    backend = FakeTranslationBackend()
    backend.register("Hello", target_lang="DE", result="Hallo")
    facade = _facade(sync_session_maker, backend)

    results = facade.translate_sync(["Hello", "Bye"], target_lang="de")

    assert [r.text for r in results] == ["Hallo", "[DE] Bye"]


def test_translate_sync_writes_its_row_through_the_sync_session(
    sync_session_maker: sessionmaker[Session],
) -> None:
    """§7.1's whole reason for existing: without a sync session the sync path
    would either skip accounting (making the character total quietly wrong) or
    wrap the async path in asyncio.run (§5.1)."""
    facade = _facade(sync_session_maker)
    user_id = uuid.uuid4()

    facade.translate_sync(["Hello"], target_lang="de", user_id=user_id)

    (row,) = _rows(sync_session_maker)
    assert row.backend == "fake"
    assert row.operation == "translate"
    assert row.outcome == "ok"
    assert row.user_id == user_id
    assert row.char_count == 5


def test_detect_sync_writes_a_detect_row(sync_session_maker: sessionmaker[Session]) -> None:
    facade = _facade(sync_session_maker)

    results = facade.detect_sync(["Bonjour"])

    assert len(results) == 1
    (row,) = _rows(sync_session_maker)
    assert row.operation == "detect"
    assert row.target_lang is None


def test_a_failing_sync_call_still_commits_its_row(
    sync_session_maker: sessionmaker[Session],
) -> None:
    backend = FakeTranslationBackend()
    backend.register_error("Boom", error=TranslationUnavailable("upstream down"))
    facade = _facade(sync_session_maker, backend)

    with pytest.raises(TranslationUnavailable):
        facade.translate_sync(["Boom"], target_lang="de")

    (row,) = _rows(sync_session_maker)
    assert row.outcome == "unavailable"
    assert row.error_code == "core.translation.unavailable"


def test_sync_budget_is_enforced_before_the_backend(
    sync_session_maker: sessionmaker[Session],
) -> None:
    backend = FakeTranslationBackend()
    facade = _facade(sync_session_maker, backend, translation_max_chars=3)

    with pytest.raises(TranslationInputTooLarge):
        facade.translate_sync(["Hello"], target_lang="de")
    with pytest.raises(TranslationInputTooLarge):
        facade.detect_sync(["Hello"])

    assert backend.calls == []
    assert _row_count(sync_session_maker) == 2


def test_sync_config_gate_writes_no_row(sync_session_maker: sessionmaker[Session]) -> None:
    facade = TranslationFacade(_settings(translation_enabled=False), None, sync_session_maker)

    with pytest.raises(TranslationNotConfigured):
        facade.translate_sync(["Hello"], target_lang="de")
    with pytest.raises(TranslationNotConfigured):
        facade.detect_sync(["Hello"])

    assert _row_count(sync_session_maker) == 0


def test_sync_empty_batch_short_circuits(sync_session_maker: sessionmaker[Session]) -> None:
    facade = _facade(sync_session_maker)

    assert facade.translate_sync([], target_lang="de") == []
    assert facade.detect_sync([]) == []
    assert _row_count(sync_session_maker) == 0


def test_sync_missing_target_lang_is_a_value_error(
    sync_session_maker: sessionmaker[Session],
) -> None:
    facade = _facade(sync_session_maker)
    with pytest.raises(ValueError, match="target_lang"):
        facade.translate_sync(["Hello"])
    assert _row_count(sync_session_maker) == 0


def test_write_call_sync_persists_a_record(sync_session_maker: sessionmaker[Session]) -> None:
    write_call_sync(
        sync_session_maker,
        CallRecord(
            user_id=None,
            backend="fake",
            operation="translate",
            source_lang="EN",
            target_lang="DE",
            text_count=1,
            char_count=5,
            latency_ms=3,
            outcome="ok",
            error_code=None,
        ),
    )

    (row,) = _rows(sync_session_maker)
    assert row.char_count == 5
    assert row.latency_ms == 3
