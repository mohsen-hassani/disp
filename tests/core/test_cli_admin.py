import uuid
from pathlib import Path

import psycopg
import pytest
from typer.testing import CliRunner

from disp.core.cli_admin import app as admin_app
from disp.core.config import get_settings

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


def _make_plant_row(conn: psycopg.Connection, user_id: uuid.UUID, name: str) -> uuid.UUID:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO plants.plant (user_id, name) VALUES (%s, %s) RETURNING id",
            (user_id, name),
        )
        plant_id = cur.fetchone()[0]
    conn.commit()
    return plant_id


def test_files_adopt_backfills_a_plant_photo_and_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DISP_FILES_ROOT", str(tmp_path / "files"))
    get_settings.cache_clear()
    try:
        with _sync_conn() as conn:
            user_id = _make_user_row(conn, "adopt-user@example.com")
            plant_id = _make_plant_row(conn, user_id, "Sansevieria")

            media_root = tmp_path / "old-media"
            media_root.mkdir()
            (media_root / f"{plant_id}.png").write_bytes(PNG_1PX)

            result = runner.invoke(
                admin_app,
                [
                    "files",
                    "adopt",
                    "--domain",
                    "plants",
                    "--purpose",
                    "plant_photo",
                    "--root",
                    str(media_root),
                ],
            )
            assert result.exit_code == 0, result.output
            assert "Adopted: 1" in result.output

            with conn.cursor() as cur:
                cur.execute("SELECT image_asset_id FROM plants.plant WHERE id = %s", (plant_id,))
                asset_id = cur.fetchone()[0]
                assert asset_id is not None

                cur.execute(
                    "SELECT owner_user_id, domain, purpose, content_type FROM core.assets "
                    "WHERE id = %s",
                    (asset_id,),
                )
                row = cur.fetchone()
                assert row == (user_id, "plants", "plant_photo", "image/png")

            # Re-running is a no-op: an already-adopted plant is skipped, not
            # duplicated.
            second = runner.invoke(
                admin_app,
                [
                    "files",
                    "adopt",
                    "--domain",
                    "plants",
                    "--purpose",
                    "plant_photo",
                    "--root",
                    str(media_root),
                ],
            )
            assert second.exit_code == 0, second.output
            assert "Adopted: 0" in second.output
            assert "Already adopted (skipped): 1" in second.output

            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM core.assets WHERE owner_user_id = %s", (user_id,))
                assert cur.fetchone()[0] == 1

            with conn.cursor() as cur:
                cur.execute("DELETE FROM core.assets WHERE owner_user_id = %s", (user_id,))
                cur.execute("DELETE FROM plants.plant WHERE id = %s", (plant_id,))
                cur.execute("DELETE FROM core.users WHERE id = %s", (user_id,))
            conn.commit()
    finally:
        get_settings.cache_clear()


def test_files_adopt_reports_orphaned_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DISP_FILES_ROOT", str(tmp_path / "files"))
    get_settings.cache_clear()
    try:
        media_root = tmp_path / "old-media"
        media_root.mkdir()
        orphan_name = f"{uuid.uuid4()}.png"
        (media_root / orphan_name).write_bytes(PNG_1PX)

        result = runner.invoke(
            admin_app,
            [
                "files",
                "adopt",
                "--domain",
                "plants",
                "--purpose",
                "plant_photo",
                "--root",
                str(media_root),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Adopted: 0" in result.output
        assert "Orphaned (no matching plant): 1" in result.output
        assert orphan_name in result.output
    finally:
        get_settings.cache_clear()


def test_files_adopt_rejects_domains_other_than_plants(tmp_path: Path) -> None:
    result = runner.invoke(
        admin_app,
        [
            "files",
            "adopt",
            "--domain",
            "notes",
            "--purpose",
            "attachment",
            "--root",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 1
    assert "only supports --domain plants" in result.output


def test_files_verify_reports_both_directions_and_deletes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DISP_FILES_ROOT", str(tmp_path))
    get_settings.cache_clear()
    try:
        with _sync_conn() as conn:
            user_id = _make_user_row(conn, "verify-user@example.com")

            # A row whose object was never written — simulates a DB-only
            # restore where the media volume didn't come back.
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO core.assets
                        (owner_user_id, domain, purpose, content_type, byte_size, sha256,
                         backend, storage_key)
                    VALUES (%s, 'plants', 'plant_photo', 'image/png', 1, %s,
                            'local', 'plants/plant_photo/never/written.png')
                    RETURNING id
                    """,
                    (user_id, "0" * 64),
                )
                missing_object_asset_id = cur.fetchone()[0]
            conn.commit()

            # An object on disk with no matching row — a genuine orphan.
            orphan_path = tmp_path / "plants" / "plant_photo" / "orphan.png"
            orphan_path.parent.mkdir(parents=True)
            orphan_path.write_bytes(PNG_1PX)

            result = runner.invoke(admin_app, ["files", "verify"])
            assert result.exit_code == 0, result.output
            assert "Rows with no backing object: 1" in result.output
            assert str(missing_object_asset_id) in result.output
            assert "Objects with no row: 1" in result.output
            assert "plants/plant_photo/orphan.png" in result.output

            # Deletes nothing (I3).
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) FROM core.assets WHERE id = %s", (missing_object_asset_id,)
                )
                assert cur.fetchone()[0] == 1
            assert orphan_path.exists()

            with conn.cursor() as cur:
                cur.execute("DELETE FROM core.assets WHERE id = %s", (missing_object_asset_id,))
                cur.execute("DELETE FROM core.users WHERE id = %s", (user_id,))
            conn.commit()
    finally:
        get_settings.cache_clear()
