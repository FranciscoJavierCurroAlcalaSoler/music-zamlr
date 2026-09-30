import os

from sqlalchemy import URL
from sqlmodel import Session, SQLModel, create_engine

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
    # creates the empty file rather than failing. Tauri (Phase 7) picks the
    # working directory itself, so this cannot stay caller-dependent.
    DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db")
    DB_PATH = os.path.join(DB_DIR, DB_FILE)

# URL.create rather than "sqlite:///" + DB_PATH, which is parsed as a URL: a
# path holding a question mark loses everything from that character onwards.
# Windows forbids one in a name, but the tests also run on Linux and macOS,
# where it is legal.
engine = create_engine(URL.create("sqlite", database=DB_PATH))


def get_session():
    with Session(engine) as session:
        yield session


def create_db_and_tables():
    os.makedirs(DB_DIR, exist_ok=True)
    SQLModel.metadata.create_all(engine)


def create_collection(collection: Collection, session: Session) -> Collection:
    session.add(collection)
    session.commit()
    session.refresh(collection)
    return collection
