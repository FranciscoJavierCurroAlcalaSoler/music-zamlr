import pytest
from sqlmodel import SQLModel, Session, create_engine


@pytest.fixture
def engine():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def session(engine):
    with Session(engine) as session:
        yield session