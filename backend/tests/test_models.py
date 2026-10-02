# tests/test_models.py
import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from models import Collection, Track


def test_collection_with_only_required_fields(session):
    collection = Collection(name="My Collection", root_path="/music/collection")
    session.add(collection)
    session.commit()
    session.refresh(collection)

    assert collection.id is not None
    assert collection.last_scanned_at is None


def test_track_with_only_required_fields(session, test_collection):
    track = Track(
        file_path="/music/song.mp3",
        file_name="song.mp3",
        bit_rate=320,
        sample_rate=44100,
        duration=210,
        file_size=8_400_000,
        collection_id=test_collection,
    )
    session.add(track)
    session.commit()
    session.refresh(track)

    assert track.id is not None
    assert track.collection_id is not None
    assert track.title is None
    assert track.file_hash is None


def test_track_missing_bit_rate_fails(session, test_collection):
    with pytest.raises(IntegrityError):
        track = Track(
            file_path="/music/song.mp3",
            file_name="song.mp3",
            sample_rate=44100,
            duration=210,
            file_size=8_400_000,
            file_hash="abc123",
            collection_id=test_collection,
        )
        session.add(track)
        session.commit()
        session.refresh(track)


def test_collection_deletion_cascades_to_tracks(session, test_collection):
    collection_id = test_collection
    track1 = Track(
        file_path="/music/song1.mp3",
        file_name="song1.mp3",
        bit_rate=320,
        sample_rate=44100,
        duration=210,
        file_size=8_400_000,
        collection_id=collection_id,
    )
    track2 = Track(
        file_path="/music/song2.mp3",
        file_name="song2.mp3",
        bit_rate=320,
        sample_rate=44100,
        duration=180,
        file_size=7_200_000,
        collection_id=collection_id,
    )
    session.add_all([track1, track2])
    session.commit()

    collection = session.get(Collection, collection_id)
    session.delete(collection)
    session.commit()

    remaining_tracks = session.exec(
        select(Track).where(Track.collection_id == collection_id)
    ).all()
    remaining_collection = session.get(Collection, collection_id)
    assert len(remaining_tracks) == 0
    assert remaining_collection is None


def test_a_bulk_delete_leaves_the_tracks_behind(session, make_track):
    # The limit of test_collection_deletion_cascades_to_tracks above,
    # pinned rather than described. It is ORM
    # behaviour: session.delete loads the children and removes them one by
    # one. A DELETE statement goes straight to SQLite, which enforces no
    # foreign keys unless PRAGMA foreign_keys=ON is set on the connection,
    # and nothing here sets it — so the tracks survive their collection.
    #
    # Named for what happens, not for what one might wish. If the pragma is
    # ever turned on, this test fails and says exactly what changed.
    collection = Collection(name="Bulk", root_path="/music/bulk")
    collection.tracks = [
        make_track(file_path="/music/bulk/one.mp3", collection_id=None)
    ]
    session.add(collection)
    session.commit()
    collection_id = collection.id

    session.exec(delete(Collection).where(Collection.id == collection_id))
    session.commit()

    assert session.exec(select(Collection)).all() == []
    orphans = session.exec(select(Track)).all()
    assert len(orphans) == 1
