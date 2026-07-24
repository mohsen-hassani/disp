import importlib
import os
from collections.abc import Callable
from logging.config import fileConfig

from alembic import context
from sqlalchemy import MetaData, create_engine, pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.sql.schema import SchemaItem

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Each branch owns exactly one schema and one models module. Importing only the
# active branch's module is what keeps `Base.metadata` scoped to that branch's
# own tables for autogenerate; `include_object` below is a defense-in-depth net
# on top of that.
BRANCH_MODELS: dict[str, str] = {
    "core": "disp.core.models",
    "notes": "disp.modules.notes.models",
}


def _active_branch() -> str:
    section = config.config_ini_section
    if section not in BRANCH_MODELS:
        raise RuntimeError(
            f"alembic must be invoked with --name=<branch>; got section {section!r}, "
            f"expected one of {sorted(BRANCH_MODELS)}"
        )
    return section


def _branch_schema(branch: str) -> str:
    schema = config.get_section_option(branch, "version_table_schema")
    if not schema:
        raise RuntimeError(f"alembic.ini section [{branch}] is missing version_table_schema")
    return schema


def _branch_version_table(branch: str) -> str:
    version_table = config.get_section_option(branch, "version_table")
    if not version_table:
        raise RuntimeError(f"alembic.ini section [{branch}] is missing version_table")
    return version_table


def _target_metadata(branch: str) -> MetaData:
    importlib.import_module(BRANCH_MODELS[branch])
    from disp.core.db import Base

    return Base.metadata


def _database_url() -> str:
    url = os.environ.get("MYSTUFF_DATABASE_URL_SYNC")
    if url:
        return url

    # Derived the same way Settings derives it (§5.2), for the common case
    # where only MYSTUFF_DATABASE_URL is set in the environment.
    database_url = os.environ.get("MYSTUFF_DATABASE_URL")
    if not database_url:
        raise RuntimeError("MYSTUFF_DATABASE_URL_SYNC is not set")
    return database_url.replace("+asyncpg", "+psycopg", 1)


def _include_object_factory(
    schema: str,
) -> Callable[[SchemaItem, str | None, str, bool, object], bool]:
    def include_object(
        object_: SchemaItem,
        name: str | None,
        type_: str,
        reflected: bool,
        compare_to: object,
    ) -> bool:
        object_schema = getattr(object_, "schema", None)
        if object_schema is not None:
            return bool(object_schema == schema)
        table = getattr(object_, "table", None)
        if table is not None:
            return bool(getattr(table, "schema", None) == schema)
        return True

    return include_object


def run_migrations_offline() -> None:
    branch = _active_branch()
    schema = _branch_schema(branch)
    target_metadata = _target_metadata(branch)

    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table=_branch_version_table(branch),
        version_table_schema=schema,
        include_schemas=True,
        include_object=_include_object_factory(schema),
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    branch = _active_branch()
    schema = _branch_schema(branch)
    target_metadata = _target_metadata(branch)

    connectable = create_engine(_database_url(), poolclass=pool.NullPool)

    with connectable.connect() as connection:
        _run_branch_migrations(connection, branch, schema, target_metadata)

    connectable.dispose()


def _run_branch_migrations(
    connection: Connection, branch: str, schema: str, target_metadata: MetaData
) -> None:
    connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
    connection.commit()

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table=_branch_version_table(branch),
        version_table_schema=schema,
        include_schemas=True,
        include_object=_include_object_factory(schema),
    )

    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
