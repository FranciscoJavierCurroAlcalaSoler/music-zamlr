# tests/test_models.py
import pytest
from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy.exc import IntegrityError

from models import Track


@pytest.fixture
def session():
    engine = create_engine("sqlite://")  # in-memory, fresh per test
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_track_with_only_required_fields(session):
    track = Track(
        file_path="/music/song.mp3",
        file_name="song.mp3",
        bit_rate=320,
        sample_rate=44100,
        duration=210,
        file_size=8_400_000,
        file_hash="abc123",
    )
    session.add(track)
    session.commit()
    session.refresh(track)

    assert track.id is not None
    assert track.title is None


def test_track_missing_bit_rate_fails(session):
    with pytest.raises(IntegrityError):
        track = Track(
            file_path="/music/song.mp3",
            file_name="song.mp3",
            sample_rate=44100,
            duration=210,
            file_size=8_400_000,
            file_hash="abc123",
        )
        session.add(track)
        session.commit()
        session.refresh(track)
