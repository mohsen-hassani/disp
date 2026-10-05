import asyncio
import uuid
from collections.abc import Iterator
from io import BytesIO

import psycopg
import pytest
from typer.testing import CliRunner

from disp.core.cli_admin import app as admin_app
from disp.core.config import get_settings
from disp.core.files.backends.s3 import S3Backend

runner = CliRunner()

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082"
)


def _sync_conn() -> psycopg.Connection:
    url = get_settings().database_url_sync.replace("+psycopg", "")
    return psycopg.connect(url)


def test_seed_admin_creates_first_admin_user() -> None:
    """A plain sync test: `seed_admin()` calls `asyncio.run()` internally,
    which cannot run from within pytest-asyncio's already-active session
    loop, so this must be a sync test. Setup/verification therefore uses a
    plain sync psycopg connection instead of the async `db_session` fixture.

    `_seed_admin` refuses unconditionally if ANY user exists anywhere in
    core.users — and by the time this runs, CLI tests elsewhere in the suite
    (tests/cli/*, which must use a real-commit session — see
    tests/cli/conftest.py) have already committed plenty of real users to
    this same container. So this test clears the table first: no other test
    depends on any specific user surviving across test *files* (each creates
    its own uniquely-named data), so this is a safe, one-off exception to
    the "never truncate shared state" rule, scoped to this one test.
    """
    with _sync_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM core.users")
        conn.commit()

    result = runner.invoke(
        admin_app,
        ["seed-admin", "--email", "admin-seed@example.com", "--display-name", "Admin Seed"],
    )
    assert result.exit_code == 0, result.output
    assert "Created admin" in result.output

    with _sync_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT is_admin FROM core.users WHERE email = %s", ("admin-seed@example.com",))
        row = cur.fetchone()
        assert row is not None
        assert row[0] is True
        cur.execute("DELETE FROM core.users WHERE email = %s", ("admin-seed@example.com",))
        conn.commit()


def test_seed_admin_refuses_when_a_user_already_exists() -> None:
    with _sync_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO core.users (email, display_name, password_hash, is_admin)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            ("existing-seed@example.com", "Existing", "x", False),
        )
        conn.commit()

    result = runner.invoke(
        admin_app,
        ["seed-admin", "--email", "new-seed@example.com", "--display-name", "New Admin"],
    )
    assert result.exit_code == 1
    assert "Refusing to seed" in result.output

    with _sync_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM core.users WHERE email = %s", ("new-seed@example.com",))
        assert cur.fetchone() is None
        cur.execute("DELETE FROM core.users WHERE email = %s", ("existing-seed@example.com",))
        conn.commit()


def _make_user_row(conn: psycopg.Connection, email: str) -> uuid.UUID:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO core.users (email, display_name, password_hash, is_admin)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (email, "Test User", "x", False),
        )
        user_id = cur.fetchone()[0]
    conn.commit()
    return user_id


def _put_object(key: str) -> None:
    backend = S3Backend.from_settings(get_settings())
    asyncio.run(backend.put(key, BytesIO(PNG_1PX), size=len(PNG_1PX), content_type="image/png"))


def _bucket_keys(prefix: str) -> set[str]:
    backend = S3Backend.from_settings(get_settings())

    async def _list() -> set[str]:
        return {key async for key, _ in backend.iter_objects(prefix)}

    return asyncio.run(_list())


def _insert_file_row(
    conn: psycopg.Connection, user_id: uuid.UUID, key: str, *, deleted: bool = False
) -> uuid.UUID:
    settings = get_settings()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO core.files
                (owner_user_id, domain, purpose, name, content_type, byte_size, sha256,
                 backend, bucket, storage_key, link_ttl_seconds, deleted_at)
            VALUES (%s, 'plants', 'plant_photo', 'x.png', 'image/png', 1, %s,
                    's3', %s, %s, 3600, CASE WHEN %s THEN now() END)
            RETURNING id
            """,
            (user_id, "0" * 64, settings.files_s3_bucket, key, deleted),
        )
        file_id = cur.fetchone()[0]
    conn.commit()
    return file_id


@pytest.fixture
def private_prefix(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """The CLI reads get_settings(); a private prefix keeps its bucket
    listing (and the sweep's deletions) away from every other test."""
    prefix = f"t-{uuid.uuid4().hex}/"
    monkeypatch.setenv("DISP_FILES_S3_PREFIX", prefix)
    get_settings.cache_clear()
    yield prefix
    get_settings.cache_clear()


def test_files_verify_reports_both_directions_and_deletes_nothing(private_prefix: str) -> None:
    with _sync_conn() as conn:
        user_id = _make_user_row(conn, f"verify-{private_prefix[:10]}@example.com")
        try:
            # A row whose object was never written — e.g. a database restored
            # from before a purge.
            missing_key = f"{private_prefix}plants/plant_photo/never-written.png"
            missing_id = _insert_file_row(conn, user_id, missing_key)
            # A healthy row + object, and a marked row awaiting purge.
            healthy_key = f"{private_prefix}plants/plant_photo/healthy.png"
            _insert_file_row(conn, user_id, healthy_key)
            _put_object(healthy_key)
            _insert_file_row(conn, user_id, f"{private_prefix}pending.png", deleted=True)
            # An object with no row — a genuine orphan.
            orphan_key = f"{private_prefix}plants/plant_photo/orphan.png"
            _put_object(orphan_key)

            result = runner.invoke(admin_app, ["files", "verify"])
            assert result.exit_code == 0, result.output
            assert "Rows with no backing object: 1" in result.output
            assert str(missing_id) in result.output
            assert "Objects with no row: 1" in result.output
            assert orphan_key in result.output
            assert "awaiting purge: 1" in result.output

            # Deletes nothing (I3).
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM core.files WHERE owner_user_id = %s", (user_id,))
                assert cur.fetchone()[0] == 3
            assert _bucket_keys(private_prefix) == {healthy_key, orphan_key}
        finally:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM core.users WHERE id = %s", (user_id,))  # cascades
            conn.commit()


def test_files_verify_reports_clean(private_prefix: str) -> None:
    result = runner.invoke(admin_app, ["files", "verify"])
    assert result.exit_code == 0, result.output
    assert "Clean" in result.output


def test_files_sweep_purges_marked_rows(private_prefix: str) -> None:
    with _sync_conn() as conn:
        user_id = _make_user_row(conn, f"sweep-{private_prefix[:10]}@example.com")
        try:
            key = f"{private_prefix}plants/plant_photo/marked.png"
            _put_object(key)
            file_id = _insert_file_row(conn, user_id, key, deleted=True)

            result = runner.invoke(admin_app, ["files", "sweep"])
            assert result.exit_code == 0, result.output
            assert "Purged rows: 1" in result.output

            assert key not in _bucket_keys(private_prefix)
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM core.files WHERE id = %s", (file_id,))
                assert cur.fetchone()[0] == 0
        finally:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM core.users WHERE id = %s", (user_id,))
            conn.commit()


def test_translation_usage_reports_recorded_calls() -> None:
    """M22-translation.md §10: this command is the *only* surface for the
    usage table — there is deliberately no HTTP route.

    Sync for the same reason as `test_seed_admin_creates_first_admin_user`
    above: the command calls `asyncio.run()` internally, so setup and
    verification go through a plain psycopg connection rather than the async
    fixtures. Rows are committed for real and deleted afterwards; a unique
    backend name keeps them out of every other test's counts.
    """
    marker = "cli-usage-test"
    with _sync_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO core.translation_call
                (backend, operation, source_lang, target_lang,
                 text_count, char_count, latency_ms, outcome)
            VALUES (%s, 'translate', 'EN', 'DE', 2, 41, 7, 'ok')
            """,
            (marker,),
        )
        conn.commit()

    try:
        result = runner.invoke(admin_app, ["translation", "usage", "--backend", marker])
        assert result.exit_code == 0, result.output
        assert marker in result.output
        assert "41 characters" in result.output
    finally:
        with _sync_conn() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM core.translation_call WHERE backend = %s", (marker,))
            conn.commit()


def test_translation_usage_says_so_when_there_is_nothing_to_report() -> None:
    result = runner.invoke(
        admin_app, ["translation", "usage", "--backend", "no-such-backend-at-all"]
    )
    assert result.exit_code == 0, result.output
    assert "No translation calls" in result.output
