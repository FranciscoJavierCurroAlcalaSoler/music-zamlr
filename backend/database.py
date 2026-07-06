import os

from sqlmodel import SQLModel, Session, create_engine

DB_FILE = "music.db"

engine = create_engine(f"sqlite:///db/{DB_FILE}")

def create_db_and_tables():
    os.makedirs("db", exist_ok=True)
    SQLModel.metadata.create_all(engine)

def database_commit(batch, engine):
    with Session(engine) as session:
        for track in batch:
            session.add(track)
        session.commit()