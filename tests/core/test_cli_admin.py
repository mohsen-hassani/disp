import psycopg
from typer.testing import CliRunner

from disp.core.cli_admin import app as admin_app
from disp.core.config import get_settings

runner = CliRunner()


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
