from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.models import metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
config.set_main_option("sqlalchemy.url", get_settings().database_url)


def include_object(object_, name, type_, reflected, compare_to):
    """Keep Alembic from managing tables owned by database extensions.

    PostGIS images may include Tiger geocoder tables. They are not part of the
    Land CRM metadata and must never be dropped by an application migration.
    """
    if type_ == "table" and reflected and compare_to is None:
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=metadata,
        literal_binds=True,
        compare_type=True,
        include_object=include_object,
        include_schemas=False,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    # Use an explicit transaction so PostgreSQL commits both the schema DDL
    # and Alembic's version row when the migration completes successfully.
    with connectable.begin() as connection:
        if connection.dialect.name == "postgresql":
            connection.exec_driver_sql("SET search_path TO public")

        context.configure(
            connection=connection,
            target_metadata=metadata,
            compare_type=True,
            include_schemas=False,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
