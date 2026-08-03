from pathlib import Path

import pytest
from sqlalchemy import create_engine as _sa_create_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import database
import main
import scanner
from models import Collection, Track


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


def _refuse_connection():
    raise RuntimeError(
        "A test opened the production database. Pass the test session in "
        "explicitly; don't import `engine` from database.py."
    )


@pytest.fixture(autouse=True)
def no_production_engine(monkeypatch):
    poisoned = _sa_create_engine("sqlite://", creator=_refuse_connection)
    for module in (database, main, scanner):
        monkeypatch.setattr(module, "engine", poisoned, raising=False)


@pytest.fixture
def engine():
    # TestClient dispatches sync endpoints to a worker thread, so the
    # session created here gets used from a different thread than it was
    # made in. check_same_thread=False lifts sqlite3's thread-ownership
    # assertion, and StaticPool makes every checkout reuse the one
    # connection, without which the worker thread would open a second
    # connection and get an empty in-memory database.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
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
        unknown = set(overrides) - set(defaults)
        if unknown:
            raise TypeError(f"make_track got unknown field(s): {sorted(unknown)}")
        defaults.update(overrides)
        return Track(**defaults)

    return _make_track


@pytest.fixture
def collections(session, tmp_path):
    mine = Collection(name="mine", root_path=str(tmp_path / "mine"))
    theirs = Collection(name="theirs", root_path=str(tmp_path / "theirs"))
    session.add(mine)
    session.add(theirs)
    session.commit()
    return mine, theirs


@pytest.fixture
def destination(tmp_path):
    path = tmp_path / "dest"
    path.mkdir()
    return path
