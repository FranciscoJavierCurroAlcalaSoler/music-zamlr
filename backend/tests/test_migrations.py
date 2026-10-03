from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from alembic import command


def test_the_migrations_match_the_models():
    """The schema the revisions build is the schema the models describe.

    Two things build this database. The tests and the app's first start use
    `SQLModel.metadata.create_all`, which reads the models; a released app
    upgrades a database it did not create, which reads the revisions. Only
    this test says the two agree, and nothing else would notice a column
    added to a model and never written into a revision — until a user's
    query asks for a column their database has never had.

    `compare_metadata` is what `alembic revision --autogenerate` uses to
    decide what to write, so a difference here is exactly the revision that
    was not written. The list it returns goes into the assertion message,
    because the failure is only useful if it names the column.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # StaticPool so every checkout is the one connection. Without it Alembic
    # would open a second one and find an empty database, since an in-memory
    # SQLite lives inside its connection and dies with it.
    connection = engine.connect()
    # An absolute path, so the test does not depend on pytest's working
    # directory, and the connection goes in the config rather than the engine
    # because env.py must not reach database.engine from a test.
    config = Config(Path(__file__).resolve().parents[1] / "alembic.ini")
    config.attributes["connection"] = connection

    try:
        command.upgrade(config, "head")
        differences = compare_metadata(
            MigrationContext.configure(connection), SQLModel.metadata
        )
        assert not differences, f"Schema drift detected: {differences}"
    finally:
        connection.close()
        engine.dispose()
