import pytest
from sqlmodel import SQLModel, Session, create_engine
from models import Collection, Track


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


@pytest.fixture
def make_track():
    def _make_track(**overrides) -> Track:
        defaults = dict(
            file_path="/fake/path.mp3",
            file_name="path.mp3",
            title="Some Title",
            artist="Some Artist",
            album="Some Album",
            track_number=1,
            year=2026,
            format="MP3",
            bit_depth=None,
            bit_rate=320000,
            sample_rate=44100,
            duration=200,
            file_size=5_000_000,
            file_hash=None,
            collection_id=1,
        )
        defaults.update(overrides)
        return Track(**defaults)

    return _make_track