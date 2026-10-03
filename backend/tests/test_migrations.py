from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, select

import database
from alembic import command
from models import Collection


def _alembic_config():
    return Config(Path(__file__).resolve().parents[1] / "alembic.ini")


def _sqlite_file_engine(path):
    # A file, not sqlite://. apply_migrations reaches the database through
    # Alembic, which opens its own connection, and an in-memory database
    # lives inside one connection and dies with it. A file is also what the
    # code under test will meet.
    return create_engine(f"sqlite:///{path}")


def test_a_new_database_gets_every_table(tmp_path, monkeypatch):
    engine = _sqlite_file_engine(tmp_path / "new.db")
    monkeypatch.setattr(database, "engine", engine)
    try:
        database.apply_migrations()

        assert {
            "collection",
            "track",
            "formatorderrow",
            "alembic_version",
        } <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_a_database_from_before_alembic_is_stamped(tmp_path, monkeypatch):
    # The row is the point of this test, not scenery. Stamping a database
    # that already has the schema and rebuilding it from the baseline both
    # end at head with the right tables, and only a row tells them apart.
    # "The schema is out of step, so recreate it" is the obvious wrong fix,
    # and on an installed copy it is the user's library.
    #
    # Not the test_collection fixture: that one writes through the session
    # fixture, whose engine is the shared in-memory database, while this
    # test migrates a file of its own that database.engine points at. The
    # row would land somewhere this test never reads.
    engine = _sqlite_file_engine(tmp_path / "existing.db")
    monkeypatch.setattr(database, "engine", engine)
    try:
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            session.add(Collection(name="Existing collection", root_path="/fake/path"))
            session.commit()

        database.apply_migrations()

        with Session(engine) as session:
            collections = session.exec(select(Collection)).all()
            assert any(item.name == "Existing collection" for item in collections)

        head = ScriptDirectory.from_config(_alembic_config()).get_current_head()
        with engine.connect() as connection:
            version = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
        assert version == head
    finally:
        engine.dispose()


def test_applying_migrations_twice_changes_nothing(tmp_path, monkeypatch):
    engine = _sqlite_file_engine(tmp_path / "twice.db")
    monkeypatch.setattr(database, "engine", engine)
    try:
        database.apply_migrations()
        tables_after_first_run = set(inspect(engine).get_table_names())

        database.apply_migrations()

        assert set(inspect(engine).get_table_names()) == tables_after_first_run
    finally:
        engine.dispose()


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
