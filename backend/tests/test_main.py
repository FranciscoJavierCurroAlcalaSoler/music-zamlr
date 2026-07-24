import pytest
from fastapi.testclient import TestClient

from database import get_session
from main import app


@pytest.fixture
def client(session):
    app.dependency_overrides[get_session] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_preview_returns_a_plan(
    client, session, tmp_path, make_track, collections, destination
):
    mine, theirs = collections

    their_track = make_track(
        file_path=str(tmp_path / "theirs" / "song.mp3"),
        collection_id=theirs.id,
        file_size=1_000_000,
        title="Only Theirs",
    )
    session.add(their_track)
    session.commit()

    response = client.post(
        "/api/import/preview",
        json={
            "track_ids": [their_track.id],
            "mine_collection_id": mine.id,
            "theirs_collection_id": theirs.id,
            "destination_root": str(destination),
            "structure_mode": "flat",
            "upgrade_action": "keep_both",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["operations"]) == 1
    assert body["operations"][0]["action"] == "copy"
    assert body["operation_counts"]["copy"] == 1
    assert body["operations"][0]["source"] == str(tmp_path / "theirs" / "song.mp3")
    assert body["operations"][0]["destination"] == str(destination / "song.mp3")
    assert body["operation_counts"]["delete"] == 0
    assert body["operation_counts"]["move"] == 0
    assert body["operation_counts"]["overwrites"] == 0


def test_already_have_track_is_rejected(
    client, session, tmp_path, make_track, collections, destination
):
    mine, theirs = collections

    # Identical tags, duration, format and bitrate on both sides (the factory
    # defaults), so the fuzzy tier pairs them and neither is an upgrade: the
    # verdict is already_have. Only file_size differs, which keeps the hash
    # tier from opening files that don't exist.
    my_track = make_track(
        collection_id=mine.id,
        file_path=str(tmp_path / "mine" / "song.mp3"),
        file_size=1_000_000,
    )
    their_track = make_track(
        collection_id=theirs.id,
        file_path=str(tmp_path / "theirs" / "song.mp3"),
        file_size=2_000_000,
    )
    session.add(my_track)
    session.add(their_track)
    session.commit()

    their_id = their_track.id

    response = client.post(
        "/api/import/preview",
        json={
            "track_ids": [their_id],
            "mine_collection_id": mine.id,
            "theirs_collection_id": theirs.id,
            "destination_root": str(destination),
            "structure_mode": "flat",
            "upgrade_action": "keep_both",
        },
    )

    assert response.status_code == 400
    assert str(their_id) in response.json()["detail"]


def test_unknown_collection_id_returns_404(client, collections, destination):
    mine, theirs = collections

    response = client.post(
        "/api/import/preview",
        json={
            "track_ids": [1],
            "mine_collection_id": mine.id,
            "theirs_collection_id": 99999,
            "destination_root": str(destination),
            "structure_mode": "flat",
            "upgrade_action": "keep_both",
        },
    )

    assert response.status_code == 404
    assert "Collection not found" in response.json()["detail"]


def test_destination_root_that_is_a_file_returns_400(client, tmp_path, collections):
    mine, theirs = collections

    destination_root = tmp_path / "not_a_dir"
    destination_root.write_text("x")

    response = client.post(
        "/api/import/preview",
        json={
            "track_ids": [1],
            "mine_collection_id": mine.id,
            "theirs_collection_id": theirs.id,
            "destination_root": str(destination_root),
            "structure_mode": "flat",
            "upgrade_action": "keep_both",
        },
    )

    assert response.status_code == 400
    assert "directory" in response.json()["detail"]


def test_same_collection_on_both_sides_returns_400(client, collections, destination):
    mine, theirs = collections

    response = client.post(
        "/api/import/preview",
        json={
            "track_ids": [1],
            "mine_collection_id": mine.id,
            "theirs_collection_id": mine.id,
            "destination_root": str(destination),
            "structure_mode": "flat",
            "upgrade_action": "keep_both",
        },
    )

    assert response.status_code == 400
    assert "own collection" in response.json()["detail"]


def test_empty_track_ids_returns_422(client, collections, destination):
    mine, theirs = collections

    response = client.post(
        "/api/import/preview",
        json={
            "track_ids": [],
            "mine_collection_id": mine.id,
            "theirs_collection_id": theirs.id,
            "destination_root": str(destination),
            "structure_mode": "flat",
            "upgrade_action": "keep_both",
        },
    )

    assert response.status_code == 422
