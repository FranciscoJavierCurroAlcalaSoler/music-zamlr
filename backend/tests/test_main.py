import json
import os
import shutil
import time

from sqlmodel import select

import main
from models import Collection, Track
from scanner import ScanProgress, ScanResult


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
    assert len(body["upgrades"]) == 0
    assert body["operations"][0]["action"] == "copy"
    assert body["operation_counts"]["copy"] == 1
    assert body["operations"][0]["source"] == str(tmp_path / "theirs" / "song.mp3")
    assert body["operations"][0]["destination"] == str(destination / "song.mp3")
    assert body["operation_counts"]["delete"] == 0
    assert body["operation_counts"]["move"] == 0
    assert body["operation_counts"]["overwrites"] == 0


def test_preview_accepts_a_destination_root_with_surrounding_whitespace(
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

    # Trailing whitespace is the dangerous half: Win32 strips it per path
    # component, so isdir and access both pass and an unstripped root would
    # ride along into every computed destination, the preview the user
    # confirms, and the log path. Linux keeps the space, so the same request
    # would 400 there instead.
    response = client.post(
        "/api/import/preview",
        json={
            "track_ids": [their_track.id],
            "mine_collection_id": mine.id,
            "theirs_collection_id": theirs.id,
            "destination_root": f"  {destination}  ",
            "structure_mode": "flat",
            "upgrade_action": "keep_both",
        },
    )

    assert response.status_code == 200
    operation = response.json()["operations"][0]
    assert operation["destination"] == os.path.normpath(str(destination / "song.mp3"))


def test_preview_with_upgrade(
    client, session, tmp_path, make_track, collections, destination
):
    # The pairing is server-derived, so this test also proves the client never sent it.
    mine, theirs = collections

    my_track = make_track(
        collection_id=mine.id,
        format="MP3",
        file_path=str(tmp_path / "mine" / "song.mp3"),
        file_size=1_000_000,
    )
    their_track = make_track(
        collection_id=theirs.id,
        format="FLAC",
        file_path=str(tmp_path / "theirs" / "song.flac"),
        file_size=2_000_000,
    )
    session.add(my_track)
    session.add(their_track)
    session.commit()

    mine_id = my_track.id
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

    assert response.status_code == 200
    body = response.json()
    assert len(body["upgrades"]) == 1
    assert body["upgrades"][0]["mine"]["id"] == mine_id
    assert body["upgrades"][0]["theirs"]["id"] == their_id


def test_preview_already_have_track_is_rejected(
    client, session, tmp_path, make_track, collections, destination
):
    mine, theirs = collections

    # Identical tags, duration, format and bitrate on both sides (the factory
    # defaults), so the fuzzy tier pairs them and neither is an upgrade: the
    # verdict is already_have. Only file_size differs, which keeps the hash
    # tier from opening files that don't exist.
    title = "A Pompous Title"
    my_track = make_track(
        collection_id=mine.id,
        file_path=str(tmp_path / "mine" / "song.mp3"),
        file_size=1_000_000,
        title=title,
    )
    their_track = make_track(
        collection_id=theirs.id,
        file_path=str(tmp_path / "theirs" / "song.mp3"),
        file_size=2_000_000,
        title=title,
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
    assert title in response.json()["detail"]


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
    title = "Any Title"
    my_track = make_track(
        collection_id=mine.id,
        file_path=str(tmp_path / "mine" / "song.mp3"),
        file_size=1_000_000,
        title=title,
    )
    their_track = make_track(
        collection_id=theirs.id,
        file_path=str(tmp_path / "theirs" / "song.mp3"),
        file_size=2_000_000,
        title=title,
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
    assert title in response.json()["detail"]

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


def test_scan_returns_collection_and_stats(scan_stream, tmp_path, fixtures_dir):
    shutil.copy(fixtures_dir / "test_track.mp3", tmp_path / "test_track.mp3")

    stream = scan_stream(
        "/api/collections/scan",
        json={"root_path": str(tmp_path), "name": "Theirs"},
    )

    body = stream.done
    assert body["scanned"] == 1
    assert body["added"] == 1
    assert body["updated"] == 0
    assert body["deleted"] == 0
    assert body["collection"]["name"] == "Theirs"


def test_scan_duplicate_collection_name_returns_400(
    client, scan_stream, tmp_path, fixtures_dir
):
    shutil.copy(fixtures_dir / "test_track.mp3", tmp_path / "test_track.mp3")

    scan_stream(
        "/api/collections/scan",
        json={"root_path": str(tmp_path), "name": "Theirs"},
    )

    response2 = client.post(
        "/api/collections/scan",
        json={"root_path": str(tmp_path), "name": "Theirs"},
    )
    assert response2.status_code == 400
    assert "already exists" in response2.json()["detail"]

    response3 = client.get("/api/collections")
    assert response3.status_code == 200
    assert len(response3.json()) == 1


def test_scan_duplicate_collection_name_is_case_insensitive(
    client, scan_stream, tmp_path, fixtures_dir
):
    shutil.copy(fixtures_dir / "test_track.mp3", tmp_path / "test_track.mp3")

    scan_stream(
        "/api/collections/scan",
        json={"root_path": str(tmp_path), "name": "Theirs"},
    )

    # Names are compared casefolded even though the unique constraint is not:
    # collection ids drive every diff and import, so a clash is cosmetic, but
    # two collections rendering identically in a dropdown is its own bug.
    second = client.post(
        "/api/collections/scan",
        json={"root_path": str(tmp_path), "name": "theirs"},
    )

    assert second.status_code == 400
    # The stored casing, not the submitted casing, so the user can see what
    # they collided with.
    assert "'Theirs'" in second.json()["detail"]


def test_scan_nonexistent_root_returns_400(client):
    response = client.post(
        "/api/collections/scan",
        json={"root_path": "/nonexistent/path", "name": "Theirs"},
    )
    assert response.status_code == 400
    assert "does not exist" in response.json()["detail"]


def test_scan_accepts_a_root_path_with_surrounding_whitespace(
    scan_stream, tmp_path, fixtures_dir
):
    shutil.copy(fixtures_dir / "test_track.mp3", tmp_path / "test_track.mp3")

    # A path pasted from Explorer or a chat message routinely carries a
    # leading or trailing space. normpath does not strip whitespace, so
    # without the validator's strip() the padded string reaches isdir and
    # the request 400s on a directory that plainly exists.
    stream = scan_stream(
        "/api/collections/scan",
        json={"root_path": f"  {tmp_path}  ", "name": "Padded"},
    )

    body = stream.done
    assert body["added"] == 1
    assert body["collection"]["root_path"] == os.path.normpath(str(tmp_path))


def test_rescan_returns_collection_and_stats(scan_stream, tmp_path, fixtures_dir):
    shutil.copy(fixtures_dir / "test_track.mp3", tmp_path / "test_track.mp3")

    first = scan_stream(
        "/api/collections/scan",
        json={"root_path": str(tmp_path), "name": "Theirs"},
    )
    collection_id = first.done["collection"]["id"]

    body = scan_stream(f"/api/collections/{collection_id}/rescan").done
    assert body["scanned"] == 1
    assert body["added"] == 0
    assert body["updated"] == 0
    assert body["deleted"] == 0


def test_rescan_unknown_collection_returns_404(client):
    response = client.post("/api/collections/99999/rescan")
    assert response.status_code == 404
    assert "Collection not found" in response.json()["detail"]


def test_rescan_triggers_deletion(scan_stream, tmp_path, fixtures_dir):
    shutil.copy(fixtures_dir / "test_track.mp3", tmp_path / "test_track.mp3")

    first = scan_stream(
        "/api/collections/scan",
        json={"root_path": str(tmp_path), "name": "Theirs"},
    )
    collection_id = first.done["collection"]["id"]

    os.remove(tmp_path / "test_track.mp3")

    body = scan_stream(f"/api/collections/{collection_id}/rescan").done
    assert body["scanned"] == 0
    assert body["added"] == 0
    assert body["updated"] == 0
    assert body["deleted"] == 1


def test_rescan_nonexistent_root_returns_400(
    client, scan_stream, tmp_path, fixtures_dir
):
    shutil.copy(fixtures_dir / "test_track.mp3", tmp_path / "test_track.mp3")

    first = scan_stream(
        "/api/collections/scan",
        json={"root_path": str(tmp_path), "name": "Theirs"},
    )
    collection_id = first.done["collection"]["id"]

    # Simulate the collection root being unmounted or deleted.
    shutil.rmtree(tmp_path)

    response2 = client.post(f"/api/collections/{collection_id}/rescan")
    assert response2.status_code == 400
    assert "not found" in response2.json()["detail"]


def test_scan_stream_ends_with_a_done_frame(scan_stream, tmp_path, fixtures_dir):
    shutil.copy(fixtures_dir / "test_track.mp3", tmp_path / "test_track.mp3")

    stream = scan_stream(
        "/api/collections/scan",
        json={"root_path": str(tmp_path), "name": "Theirs"},
    )

    # The sequence, not the count. A fixture folder scans in microseconds, so
    # the poll loop can finish before any progress exists and zero progress
    # frames is a correct stream. Asserting a count here passes on a slow
    # machine and fails on a fast one.
    assert stream.events[-1] == "done"
    assert set(stream.events[:-1]) <= {"progress"}
    assert stream.events.count("done") == 1
    assert stream.error is None


def test_scan_stream_reports_progress_frames(scan_stream, monkeypatch, tmp_path):
    # A real scan is far too fast to observe, so the poll interval shrinks and
    # the scan is slowed. The margin is deliberate: the scan outlasts the poll
    # by 300x, which is what keeps this from being a race dressed as a test.
    monkeypatch.setattr(main, "PROGRESS_INTERVAL_SECONDS", 0.001)

    def slow_scan(root_path, collection_id, session, on_progress=None):
        on_progress(
            ScanProgress(
                scanned=7,
                added=3,
                skipped_non_audio=1,
                updated=1,
                deleted=0,
                matched=2,
                # A Windows path, so this also pins that json.dumps escapes
                # the backslashes rather than breaking the frame.
                current_path=r"C:\music\Radiohead\Creep.mp3",
            )
        )
        time.sleep(0.3)
        return ScanResult(
            scanned=7,
            added=3,
            skipped_non_audio=1,
            updated=1,
            deleted=0,
            matched=2,
            collection=session.get(Collection, collection_id),
        )

    monkeypatch.setattr(main, "scan_folder", slow_scan)

    stream = scan_stream(
        "/api/collections/scan",
        json={"root_path": str(tmp_path), "name": "Theirs"},
    )

    assert stream.progress
    assert stream.progress[-1] == {
        "scanned": 7,
        "added": 3,
        "skipped_non_audio": 1,
        "updated": 1,
        "deleted": 0,
        "matched": 2,
        "current_path": r"C:\music\Radiohead\Creep.mp3",
    }
    assert stream.done["scanned"] == 7


def test_scan_stream_reports_a_scan_failure_as_an_error_frame(
    scan_stream, monkeypatch, caplog, tmp_path
):
    def exploding_scan(root_path, collection_id, session, on_progress=None):
        raise OSError("the drive went away")

    monkeypatch.setattr(main, "scan_folder", exploding_scan)

    stream = scan_stream(
        "/api/collections/scan",
        json={"root_path": str(tmp_path), "name": "Theirs"},
    )

    # A 200 carrying an error frame, not a 500. Once the stream opens the
    # status is already sent and cannot be taken back, so a failure after that
    # point has nowhere else to go.
    assert stream.done is None
    assert stream.events[-1] == "error"
    assert stream.error == {"detail": "the drive went away"}
    # The catch is broad, which the project's convention normally forbids. It
    # is allowed here only because the traceback still reaches the log, so a
    # bug is as loud as it was before, just in a different place.
    assert "Scan of" in caplog.text
    assert "OSError" in caplog.text


def test_scan_validation_failure_never_opens_a_stream(client):
    response = client.post(
        "/api/collections/scan",
        json={"root_path": "/nonexistent/path", "name": "Theirs"},
    )

    # Every guard runs before the StreamingResponse is returned, so a bad
    # request still gets a real status and a JSON detail. If a guard ever
    # moves after the stream opens this becomes a 200 event-stream, and
    # throwForResponse in api.ts stops seeing failures entirely.
    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/json")


def test_rescan_commit_from_the_worker_thread_is_visible(
    scan_stream, session, tmp_path, fixtures_dir
):
    shutil.copy(fixtures_dir / "test_track.mp3", tmp_path / "test_track.mp3")

    first = scan_stream(
        "/api/collections/scan",
        json={"root_path": str(tmp_path), "name": "Theirs"},
    )
    collection_id = first.done["collection"]["id"]
    session.expire_all()
    before = session.get(Collection, collection_id).last_scanned_at
    assert before is not None

    scan_stream(f"/api/collections/{collection_id}/rescan")

    # Expire before reading, every time. Whether this session would otherwise
    # answer from its identity map depends on where its own transaction
    # happened to end, which is not something a test should rely on in either
    # direction. What is asserted here is the part that must hold: a commit
    # made on the worker thread's own Session reaches the request side.
    session.expire_all()
    assert session.get(Collection, collection_id).last_scanned_at > before


def _import_body(mine, theirs, destination, track_ids, resolutions=None, **overrides):
    body = {
        "track_ids": track_ids,
        "mine_collection_id": mine.id,
        "theirs_collection_id": theirs.id,
        "destination_root": str(destination),
        "structure_mode": "flat",
        "upgrade_action": "keep_both",
    }
    if resolutions is not None:
        body["resolutions"] = resolutions
    body.update(overrides)
    return body


def test_ambiguous_track_without_a_resolution_is_rejected(
    client, collections, destination, make_ambiguity
):
    mine, theirs = collections
    ambiguity = make_ambiguity()
    their_track = ambiguity.theirs[0]

    response = client.post(
        "/api/import/preview",
        json=_import_body(mine, theirs, destination, [their_track.id]),
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    # Names the track and says what to do, rather than just refusing: this is
    # the message a user sees for every unresolved review row.
    assert "Not import candidates" in detail
    assert their_track.file_name in detail
    assert "run Compare again" in detail


def test_resolution_none_of_these_routes_to_missing(
    client, collections, destination, make_ambiguity
):
    mine, theirs = collections
    ambiguity = make_ambiguity()
    their_track = ambiguity.theirs[0]

    response = client.post(
        "/api/import/preview",
        json=_import_body(
            mine,
            theirs,
            destination,
            [their_track.id],
            resolutions=[{"theirs_id": their_track.id, "mine_id": None}],
        ),
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["operations"]) == 1
    assert body["operations"][0]["action"] == "copy"
    assert body["operations"][0]["source"] == their_track.file_path
    # The point of "none of these": routed to missing, not paired with either
    # candidate. Without this the test passes even on a wrong pairing, since
    # an upgrade also produces a copy.
    assert body["upgrades"] == []


def test_resolution_deletes_the_chosen_file_only(
    client, collections, destination, make_ambiguity
):
    mine, theirs = collections
    ambiguity = make_ambiguity(theirs_format="FLAC", mine_format="MP3")
    their_track = ambiguity.theirs[0]
    chosen, not_chosen = ambiguity.candidates

    response = client.post(
        "/api/import/preview",
        json=_import_body(
            mine,
            theirs,
            destination,
            [their_track.id],
            resolutions=[{"theirs_id": their_track.id, "mine_id": chosen.id}],
            upgrade_action="delete",
        ),
    )

    assert response.status_code == 200
    body = response.json()
    # Copy first, then the destructive step: the order is the safety
    # mechanism, not a formatting detail (§5b).
    assert [op["action"] for op in body["operations"]] == ["copy", "delete"]
    assert body["operations"][0]["source"] == their_track.file_path
    assert body["operations"][1]["source"] == chosen.file_path
    assert not_chosen.file_path not in {op["source"] for op in body["operations"]}


def test_resolution_naming_a_file_that_is_not_a_candidate_is_rejected(
    client, session, tmp_path, make_track, collections, destination, make_ambiguity
):
    mine, theirs = collections
    ambiguity = make_ambiguity()
    their_track = ambiguity.theirs[0]

    unrelated = make_track(
        collection_id=mine.id,
        file_path=str(tmp_path / "mine" / "unrelated.mp3"),
        file_name="unrelated.mp3",
        title="A Different One",
        artist="Somebody Else",
        duration=300,
        file_size=99_000_000,
    )
    session.add(unrelated)
    session.commit()

    response = client.post(
        "/api/import/preview",
        json=_import_body(
            mine,
            theirs,
            destination,
            [their_track.id],
            resolutions=[{"theirs_id": their_track.id, "mine_id": unrelated.id}],
        ),
    )

    # The §5c guard: the server re-derives the candidate set, so a client can
    # only ever pick a wrong candidate among genuine ones, never any file it
    # likes. If this ever passes silently the protection is gone.
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert unrelated.file_name in detail
    assert their_track.file_name in detail
    assert "not one of the files matched" in detail


def test_two_resolutions_claiming_the_same_file_are_rejected(
    client, collections, destination, make_ambiguity
):
    mine, theirs = collections
    # Two tracks of theirs sharing one candidate set, so both can name the
    # same file of mine. FLAC over MP3 so both classify as upgrades and
    # actually reach the double-booking check.
    ambiguity = make_ambiguity(theirs_format="FLAC", mine_format="MP3", theirs_count=2)
    first, second = ambiguity.theirs
    contested = ambiguity.candidates[0]

    response = client.post(
        "/api/import/preview",
        json=_import_body(
            mine,
            theirs,
            destination,
            [first.id, second.id],
            resolutions=[
                {"theirs_id": first.id, "mine_id": contested.id},
                {"theirs_id": second.id, "mine_id": contested.id},
            ],
            upgrade_action="delete",
        ),
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    # Both tracks of theirs share artist and title — that is why they matched
    # the same file — so the message has to name them by file to be usable.
    # Pins which check fired: several other conditions also return 400, so a
    # bare status assertion would pass on the wrong rejection.
    assert "would both replace" in detail
    assert first.file_name in detail
    assert second.file_name in detail
    assert contested.file_name in detail


def test_resolution_to_a_better_file_of_mine_is_rejected(
    client, collections, destination, make_ambiguity
):
    mine, theirs = collections
    # Theirs is the lossy one, so either candidate of mine wins on quality.
    ambiguity = make_ambiguity(theirs_format="MP3", mine_format="FLAC")
    their_track = ambiguity.theirs[0]
    chosen = ambiguity.candidates[0]

    response = client.post(
        "/api/import/preview",
        json=_import_body(
            mine,
            theirs,
            destination,
            [their_track.id],
            resolutions=[{"theirs_id": their_track.id, "mine_id": chosen.id}],
        ),
    )

    # Refusing is right — copying would hand back a worse duplicate — but the
    # generic "not import candidates" message would list three reasons that
    # all happen to be false here, so this path has its own.
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "Nothing to import" in detail
    assert their_track.file_name in detail
