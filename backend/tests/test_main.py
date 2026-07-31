import json
import os

import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

from database import get_session
from main import app
from models import Track


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
    assert "collection against itself" in response.json()["detail"]


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


def test_empty_destination_root_returns_422(client, collections):
    # normpath("") is ".", a real writable directory, so an empty root that
    # reached the endpoint's isdir and access checks would pass them and
    # import into the server's working directory. The schema rejects it
    # before normalizing, which is why this is a 422 and not a 400.
    mine, theirs = collections

    response = client.post(
        "/api/import/preview",
        json={
            "track_ids": [1],
            "mine_collection_id": mine.id,
            "theirs_collection_id": theirs.id,
            "destination_root": "",
            "structure_mode": "flat",
            "upgrade_action": "keep_both",
        },
    )

    assert response.status_code == 422


def test_whitespace_destination_root_returns_422(client, collections):
    mine, theirs = collections
    response = client.post(
        "/api/import/preview",
        json={
            "track_ids": [1],
            "mine_collection_id": mine.id,
            "theirs_collection_id": theirs.id,
            "destination_root": "   ",
            "structure_mode": "flat",
            "upgrade_action": "keep_both",
        },
    )
    assert response.status_code == 422


def test_execute_copies_a_missing_track(
    client, session, tmp_path, make_track, collections, destination
):
    mine, theirs = collections

    their_dir = tmp_path / "theirs"
    their_dir.mkdir()
    source_file = their_dir / "song.mp3"
    source_file.write_bytes(b"audio data")

    their_track = make_track(
        file_path=str(source_file),
        collection_id=theirs.id,
        file_size=1_000_000,
        title="Only Theirs",
    )
    session.add(their_track)
    session.commit()

    their_id = their_track.id

    response = client.post(
        "/api/import/execute",
        json={
            "track_ids": [their_id],
            "mine_collection_id": mine.id,
            "theirs_collection_id": theirs.id,
            "destination_root": str(destination),
            "structure_mode": "flat",
            "upgrade_action": "keep_both",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status_counts"]["success"] == 1
    assert body["status_counts"]["failed"] == 0
    assert body["operations"][0]["status"] == "success"
    assert (destination / "song.mp3").read_bytes() == b"audio data"


def test_execute_returns_status_counts(
    client, session, tmp_path, make_track, collections, destination
):
    mine, theirs = collections

    their_dir = tmp_path / "theirs"
    their_dir.mkdir()
    source_file = their_dir / "song.mp3"
    source_file.write_bytes(b"audio data")

    their_track = make_track(
        file_path=str(source_file),
        collection_id=theirs.id,
        file_size=1_000_000,
        title="Only Theirs",
    )
    session.add(their_track)
    session.commit()

    their_id = their_track.id

    response = client.post(
        "/api/import/execute",
        json={
            "track_ids": [their_id],
            "mine_collection_id": mine.id,
            "theirs_collection_id": theirs.id,
            "destination_root": str(destination),
            "structure_mode": "flat",
            "upgrade_action": "keep_both",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status_counts"]["success"] == 1
    assert body["status_counts"]["failed"] == 0
    assert body["status_counts"]["skipped"] == 0


def test_copied_files_get_no_track_rows(
    client, session, tmp_path, make_track, collections, destination
):
    mine, theirs = collections

    their_dir = tmp_path / "theirs"
    their_dir.mkdir()
    source_file = their_dir / "song.mp3"
    source_file.write_bytes(b"audio data")

    their_track = make_track(
        file_path=str(source_file),
        collection_id=theirs.id,
        file_size=1_000_000,
        title="Only Theirs",
    )
    session.add(their_track)
    session.commit()

    their_id = their_track.id
    tracks_before = len(session.exec(select(Track)).all())

    response = client.post(
        "/api/import/execute",
        json={
            "track_ids": [their_id],
            "mine_collection_id": mine.id,
            "theirs_collection_id": theirs.id,
            "destination_root": str(destination),
            "structure_mode": "flat",
            "upgrade_action": "keep_both",
        },
    )

    rows = session.exec(
        select(Track).where(Track.file_path == str(destination / "song.mp3"))
    ).all()

    assert response.status_code == 200
    assert (destination / "song.mp3").exists()

    # Imported files are deliberately not registered: destination_root can be
    # any folder, so nothing guarantees it sits inside mine's collection tree.
    # A re-scan is how they become visible.
    assert len(session.exec(select(Track)).all()) == tracks_before
    assert rows == []


def test_delete_action_removes_the_track_row(
    client, session, tmp_path, make_track, collections, destination
):
    mine, theirs = collections

    their_dir = tmp_path / "theirs"
    their_dir.mkdir()
    source_file_theirs = their_dir / "their_song.mp3"
    source_file_theirs.write_bytes(b"their audio data")

    mine_dir = tmp_path / "mine"
    mine_dir.mkdir()
    source_file_mine = mine_dir / "mine_song.mp3"
    source_file_mine.write_bytes(b"my audio data")

    their_track = make_track(
        file_path=str(source_file_theirs),
        collection_id=theirs.id,
        file_size=1_000_000,
        bit_rate=640000,
        title="A Short Song",
        artist="Johnny Singer",
    )

    mine_track = make_track(
        file_path=str(source_file_mine),
        collection_id=mine.id,
        file_size=1_000_000,
        bit_rate=320000,
        title="A Short Song",
        artist="Johnny Singer",
    )
    session.add(their_track)
    session.add(mine_track)
    session.commit()

    their_id = their_track.id
    mine_id = mine_track.id

    response = client.post(
        "/api/import/execute",
        json={
            "track_ids": [their_id],
            "mine_collection_id": mine.id,
            "theirs_collection_id": theirs.id,
            "destination_root": str(destination),
            "structure_mode": "flat",
            "upgrade_action": "delete",
        },
    )

    assert response.status_code == 200
    assert (destination / "their_song.mp3").exists()
    assert not source_file_mine.exists()
    assert session.get(Track, mine_id) is None


def test_move_action_removes_the_track_row(
    client, session, tmp_path, make_track, collections, destination
):
    mine, theirs = collections

    their_dir = tmp_path / "theirs"
    their_dir.mkdir()
    source_file_theirs = their_dir / "their_song.mp3"
    source_file_theirs.write_bytes(b"their audio data")

    mine_dir = tmp_path / "mine"
    mine_dir.mkdir()
    source_file_mine = mine_dir / "mine_song.mp3"
    source_file_mine.write_bytes(b"my audio data")

    their_track = make_track(
        file_path=str(source_file_theirs),
        collection_id=theirs.id,
        file_size=1_000_000,
        bit_rate=640000,
        title="A Short Song",
        artist="Johnny Singer",
    )

    mine_track = make_track(
        file_path=str(source_file_mine),
        collection_id=mine.id,
        file_size=1_000_000,
        bit_rate=320000,
        title="A Short Song",
        artist="Johnny Singer",
    )
    session.add(their_track)
    session.add(mine_track)
    session.commit()

    their_id = their_track.id
    mine_id = mine_track.id

    response = client.post(
        "/api/import/execute",
        json={
            "track_ids": [their_id],
            "mine_collection_id": mine.id,
            "theirs_collection_id": theirs.id,
            "destination_root": str(destination),
            "structure_mode": "flat",
            "upgrade_action": "move",
        },
    )

    assert response.status_code == 200
    assert (destination / "their_song.mp3").exists()
    assert (destination / "_superseded" / "mine_song.mp3").exists()
    assert session.get(Track, mine_id) is None


def test_keep_both_leaves_my_row_and_file(
    client, session, tmp_path, make_track, collections, destination
):
    mine, theirs = collections

    their_dir = tmp_path / "theirs"
    their_dir.mkdir()
    source_file_theirs = their_dir / "their_song.mp3"
    source_file_theirs.write_bytes(b"their audio data")

    mine_dir = tmp_path / "mine"
    mine_dir.mkdir()
    source_file_mine = mine_dir / "mine_song.mp3"
    source_file_mine.write_bytes(b"my audio data")

    their_track = make_track(
        file_path=str(source_file_theirs),
        collection_id=theirs.id,
        file_size=1_000_000,
        bit_rate=640000,
        title="A Short Song",
        artist="Johnny Singer",
    )

    mine_track = make_track(
        file_path=str(source_file_mine),
        collection_id=mine.id,
        file_size=1_000_000,
        bit_rate=320000,
        title="A Short Song",
        artist="Johnny Singer",
    )
    session.add(their_track)
    session.add(mine_track)
    session.commit()

    their_id = their_track.id
    mine_id = mine_track.id

    response = client.post(
        "/api/import/execute",
        json={
            "track_ids": [their_id],
            "mine_collection_id": mine.id,
            "theirs_collection_id": theirs.id,
            "destination_root": str(destination),
            "structure_mode": "flat",
            "upgrade_action": "keep_both",
        },
    )

    assert response.status_code == 200
    assert (destination / "their_song.mp3").exists()
    assert source_file_mine.exists()
    assert not (destination / "_superseded" / "mine_song.mp3").exists()
    assert session.get(Track, mine_id) is not None


def test_failed_copy_returns_200_with_failed_status(
    client, session, tmp_path, make_track, collections, destination
):
    mine, theirs = collections

    their_dir = tmp_path / "theirs"
    their_dir.mkdir()
    source_file_theirs = their_dir / "their_song.mp3"
    source_file_theirs.write_bytes(b"their audio data")

    their_track = make_track(
        file_path=str(source_file_theirs),
        collection_id=theirs.id,
        file_size=1_000_000,
        bit_rate=640000,
        title="A Short Song",
        artist="Johnny Singer",
    )

    session.add(their_track)
    session.commit()

    their_id = their_track.id

    os.remove(source_file_theirs)

    response = client.post(
        "/api/import/execute",
        json={
            "track_ids": [their_id],
            "mine_collection_id": mine.id,
            "theirs_collection_id": theirs.id,
            "destination_root": str(destination),
            "structure_mode": "flat",
            "upgrade_action": "keep_both",
        },
    )

    assert response.status_code == 200
    assert not (destination / "their_song.mp3").exists()
    body = response.json()
    assert body["status_counts"]["success"] == 0
    assert body["status_counts"]["failed"] == 1
    assert body["status_counts"]["skipped"] == 0


def test_failed_copy_skips_the_delete_and_keeps_my_file(
    client, session, tmp_path, make_track, collections, destination
):
    mine, theirs = collections

    their_dir = tmp_path / "theirs"
    their_dir.mkdir()
    source_file_theirs = their_dir / "their_song.mp3"
    source_file_theirs.write_bytes(b"their audio data")

    mine_dir = tmp_path / "mine"
    mine_dir.mkdir()
    source_file_mine = mine_dir / "mine_song.mp3"
    source_file_mine.write_bytes(b"my audio data")

    their_track = make_track(
        file_path=str(source_file_theirs),
        collection_id=theirs.id,
        file_size=1_000_000,
        bit_rate=640000,
        title="A Short Song",
        artist="Johnny Singer",
    )

    mine_track = make_track(
        file_path=str(source_file_mine),
        collection_id=mine.id,
        file_size=2_000_000,
        bit_rate=320000,
        title="A Short Song",
        artist="Johnny Singer",
    )

    session.add(their_track)
    session.add(mine_track)
    session.commit()

    their_id = their_track.id
    mine_id = mine_track.id

    os.remove(source_file_theirs)

    response = client.post(
        "/api/import/execute",
        json={
            "track_ids": [their_id],
            "mine_collection_id": mine.id,
            "theirs_collection_id": theirs.id,
            "destination_root": str(destination),
            "structure_mode": "flat",
            "upgrade_action": "delete",
        },
    )

    assert response.status_code == 200
    assert not (destination / "their_song.mp3").exists()
    assert source_file_mine.exists()
    body = response.json()
    assert body["status_counts"]["success"] == 0
    assert body["status_counts"]["failed"] == 1
    assert body["status_counts"]["skipped"] == 1
    assert session.get(Track, mine_id) is not None


def test_one_failed_group_does_not_stop_another(
    client, session, tmp_path, make_track, collections, destination
):
    mine, theirs = collections

    their_dir = tmp_path / "theirs"
    their_dir.mkdir()
    source_file_theirs_g0 = their_dir / "their_song_g0.mp3"
    source_file_theirs_g0.write_bytes(b"their audio data g0")
    source_file_theirs_g1 = their_dir / "their_song_g1.mp3"
    source_file_theirs_g1.write_bytes(b"their audio data g1")

    mine_dir = tmp_path / "mine"
    mine_dir.mkdir()
    source_file_mine_g0 = mine_dir / "mine_song_g0.mp3"
    source_file_mine_g0.write_bytes(b"my audio data g0")
    source_file_mine_g1 = mine_dir / "mine_song_g1.mp3"
    source_file_mine_g1.write_bytes(b"my audio data g1")

    their_track_g0 = make_track(
        file_path=str(source_file_theirs_g0),
        collection_id=theirs.id,
        file_size=1_000_000,
        bit_rate=640000,
        title="A Short Song G0",
        artist="Johnny Singer",
    )

    their_track_g1 = make_track(
        file_path=str(source_file_theirs_g1),
        collection_id=theirs.id,
        file_size=10_000_000,
        bit_rate=640000,
        title="A Short Song G1",
        artist="Johnny Singer",
    )

    mine_track_g0 = make_track(
        file_path=str(source_file_mine_g0),
        collection_id=mine.id,
        file_size=2_000_000,
        bit_rate=320000,
        title="A Short Song G0",
        artist="Johnny Singer",
    )

    mine_track_g1 = make_track(
        file_path=str(source_file_mine_g1),
        collection_id=mine.id,
        file_size=20_000_000,
        bit_rate=320000,
        title="A Short Song G1",
        artist="Johnny Singer",
    )

    session.add(their_track_g0)
    session.add(their_track_g1)
    session.add(mine_track_g0)
    session.add(mine_track_g1)
    session.commit()

    their_id_g0 = their_track_g0.id
    their_id_g1 = their_track_g1.id
    mine_id_g0 = mine_track_g0.id
    mine_id_g1 = mine_track_g1.id

    os.remove(source_file_theirs_g0)

    response = client.post(
        "/api/import/execute",
        json={
            "track_ids": [their_id_g0, their_id_g1],
            "mine_collection_id": mine.id,
            "theirs_collection_id": theirs.id,
            "destination_root": str(destination),
            "structure_mode": "flat",
            "upgrade_action": "delete",
        },
    )

    assert response.status_code == 200
    assert not (destination / "their_song_g0.mp3").exists()
    assert (destination / "their_song_g1.mp3").exists()
    assert source_file_mine_g0.exists()
    assert not source_file_mine_g1.exists()
    body = response.json()
    assert body["status_counts"]["success"] == 2
    assert body["status_counts"]["failed"] == 1
    assert body["status_counts"]["skipped"] == 1
    assert session.get(Track, mine_id_g0) is not None
    assert session.get(Track, mine_id_g1) is None


def test_log_file_is_written_to_destination_root(
    client, session, tmp_path, make_track, collections, destination
):
    mine, theirs = collections

    their_dir = tmp_path / "theirs"
    their_dir.mkdir()
    source_file = their_dir / "song.mp3"
    source_file.write_bytes(b"audio data")

    their_track = make_track(
        file_path=str(source_file),
        collection_id=theirs.id,
        file_size=1_000_000,
        title="Only Theirs",
    )
    session.add(their_track)
    session.commit()

    their_id = their_track.id

    response = client.post(
        "/api/import/execute",
        json={
            "track_ids": [their_id],
            "mine_collection_id": mine.id,
            "theirs_collection_id": theirs.id,
            "destination_root": str(destination),
            "structure_mode": "flat",
            "upgrade_action": "keep_both",
        },
    )

    assert response.status_code == 200
    assert response.json()["log_error"] is None

    logs = list(destination.glob("import_log_*.json"))
    assert len(logs) == 1

    entries = json.loads(logs[0].read_text())
    assert len(entries) == 1
    assert entries[0]["status"] == "success"
    assert entries[0]["operation"]["action"] == "copy"

    assert response.json()["log_path"] == str(logs[0])


def test_execute_rejects_a_non_candidate_id(
    client, session, tmp_path, make_track, collections, destination
):
    mine, theirs = collections

    # Identical tags, duration, format and bitrate on both sides, so the
    # fuzzy tier pairs them and neither wins: the verdict is already_have,
    # which is not an import candidate. Only file_size differs, which keeps
    # the hash tier from opening files.
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
        "/api/import/execute",
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

    # Nothing ran: validation happens before any file is touched.
    assert list(destination.iterdir()) == []


def test_diff_buckets_a_missing_track(
    client, session, tmp_path, make_track, collections
):
    mine, theirs = collections

    # One track only theirs has. GET, so the parameter names below are part
    # of the URL contract the frontend depends on: renaming them breaks
    # DiffView with a 422 and nothing else would notice.
    their_track = make_track(
        file_path=str(tmp_path / "theirs" / "song.mp3"),
        collection_id=theirs.id,
        file_size=1_000_000,
        title="Only Theirs",
    )
    session.add(their_track)
    session.commit()

    their_id = their_track.id

    response = client.get(f"/api/diff?mine={mine.id}&theirs={theirs.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["match_counts"]["missing"] == 1
    assert body["match_counts"]["already_have"] == 0
    assert body["match_counts"]["only_in_mine"] == 0
    assert [t["id"] for t in body["match_results"]["missing"]] == [their_id]


def test_diff_unknown_collection_returns_404(client, collections):
    mine, theirs = collections
    response = client.get(f"/api/diff?mine={mine.id}&theirs=99999")
    assert response.status_code == 404


def test_diff_same_collection_returns_400(client, collections):
    mine, theirs = collections
    response = client.get(f"/api/diff?mine={mine.id}&theirs={mine.id}")
    assert response.status_code == 400
