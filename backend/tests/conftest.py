import pytest
from sqlmodel import SQLModel, Session, create_engine
from models import Collection


@pytest.fixture
def engine():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def session(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture
def test_collection(session: Session) -> int:
    collection = Collection(
        name="test-collection",
        root_path="/fake/path",
    )
    session.add(collection)
    session.commit()
    session.refresh(collection)
    return collection.id