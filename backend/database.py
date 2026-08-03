import os

from sqlmodel import Session, SQLModel, create_engine

from models import Collection

DB_FILE = "music.db"

engine = create_engine(f"sqlite:///db/{DB_FILE}")


def get_session():
    with Session(engine) as session:
        yield session


def create_db_and_tables():
    os.makedirs("db", exist_ok=True)
    SQLModel.metadata.create_all(engine)


def create_collection(collection: Collection, session: Session) -> Collection:
    session.add(collection)
    session.commit()
    session.refresh(collection)
    return collection
