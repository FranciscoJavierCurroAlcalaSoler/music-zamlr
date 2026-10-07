import os
import sqlite3

from alembic.config import Config
from sqlalchemy import URL, event, inspect
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine

from alembic import command
from launch_settings import read_launch_settings
from models import Collection

launch_settings = read_launch_settings(os.environ)

if launch_settings.database_path:
    DB_PATH = launch_settings.database_path
    DB_DIR = os.path.dirname(DB_PATH)
else:
    DB_FILE = "music.db"
    # Anchored to this file's own directory, not the working directory: a
    # relative "db/music.db" silently resolves to a different database when the
    # server is started from the repo root instead of backend/, and SQLite
    # creates the empty file rather than failing. The desktop shell picks
    # the working directory itself, so this cannot depend on the caller.
    DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db")
    DB_PATH = os.path.join(DB_DIR, DB_FILE)

# URL.create rather than "sqlite:///" + DB_PATH, which is parsed as a URL: a
# path holding a question mark loses everything from that character onwards.
# Windows forbids one in a name, but the tests also run on Linux and macOS,
# where it is legal.
engine = create_engine(URL.create("sqlite", database=DB_PATH))

# Anchored to this file for the reason DB_DIR is: the working directory
# belongs to whoever started the process, and the shell picks its own. In a
# frozen build this directory is the one PyInstaller unpacks into, which is
# where music-zamlr-backend.spec puts alembic.ini and the revisions.
ALEMBIC_INI_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "alembic.ini"
)

# The revision whose schema a database made before Alembic already has. It
# never moves: every later revision goes on top of it.
BASELINE_REVISION = "7159e92fa59d"


@event.listens_for(Engine, "connect")
def _enforce_foreign_keys(dbapi_connection, connection_record):
    """Ask SQLite to apply the foreign keys the schema already declares.

    SQLite reads this setting per connection and forgets it when the
    connection closes, so it cannot be a statement run once at startup.
    Off, `DELETE FROM collection` leaves that collection's tracks behind,
    pointing at a row that no longer exists, and a track can name a
    collection that never existed at all. The ORM cascade hides neither:
    it only fires for `session.delete`, which loads the children and
    removes them one at a time.

    On the Engine class rather than on this module's engine, because the
    tests build their own. A hook bound to one engine would leave the whole
    suite running without the rule the shipped application runs with, which
    is a suite that passes by testing something else.

    The guard is not ceremony. This fires for every engine in the process,
    including one a library makes, and a SQLite pragma sent elsewhere is a
    statement the next reader cannot account for.
    """
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_session():
    with Session(engine) as session:
        yield session


def apply_migrations() -> None:
    """Bring the database at DB_PATH to the newest revision.

    Three states arrive here. A database with tables and no version table
    was built by an earlier version of this program, before there were any
    revisions. Its tables match the baseline, so it is stamped at the
    baseline and then upgraded like every other database. Upgrading it
    without the stamp would run the baseline's create_table against tables
    that exist and stop on "table collection already exists". Stamping it at
    head instead would mark every later revision as done, and the columns
    they add would never arrive. The other two states are only upgraded: a
    file with nothing in it, where the baseline creates the schema, and a
    database already carrying a version, where whatever is newer runs.

    `and table_names` is what separates the first state from an empty file.
    Without it a new database is stamped at the baseline while holding
    nothing, and the upgrade runs only the later revisions, against tables
    that were never created.
    """
    # SQLite makes a database file but not the directory above it, and the
    # shell names a folder in app-data that has never existed.
    os.makedirs(DB_DIR, exist_ok=True)
    config = Config(ALEMBIC_INI_PATH)
    table_names = inspect(engine).get_table_names()

    if "alembic_version" not in table_names and table_names:
        command.stamp(config, BASELINE_REVISION)

    command.upgrade(config, "head")


def create_collection(collection: Collection, session: Session) -> Collection:
    session.add(collection)
    session.commit()
    session.refresh(collection)
    return collection
