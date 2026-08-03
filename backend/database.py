import os

from sqlmodel import Session, SQLModel, create_engine

from models import Collection

DB_FILE = "music.db"
# Anchored to this file's own directory, not the working directory: a
# relative "db/music.db" silently resolves to a different database when the
# server is started from the repo root instead of backend/, and SQLite
# creates the empty file rather than failing. Tauri (Phase 7) picks the
# working directory itself, so this cannot stay caller-dependent.
DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db")
DB_PATH = os.path.join(DB_DIR, DB_FILE)

engine = create_engine(f"sqlite:///{DB_PATH}")


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
