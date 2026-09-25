import json
import os
import shutil
import time
import types

import pytest
from fastapi import HTTPException
from sqlmodel import select

import main
from enums import ActionType, ImportPhase
from fingerprinting import FPCALC_ALGORITHM, FPCALC_LENGTH_SECONDS, pack_fingerprint
from importing import ExecuteProgress, PlannedOperation
from matching import DiffProgress, MatchResult
from models import Collection, FormatOrderRow, Track
from scanner import ScanProgress, ScanResult


def test_preview_returns_a_plan(
    session, tmp_path, make_track, collections, destination, event_stream
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

    stream = event_stream(
        "/api/import/preview",
        "POST",
        json={
            "track_ids": [their_track.id],
            "mine_collection_id": mine.id,
            "theirs_collection_id": theirs.id,
            "destination_root": str(destination),
            "structure_mode": "flat",
            "upgrade_action": "keep_both",
        },
    )

    body = stream.done
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
    session, tmp_path, make_track, collections, destination, event_stream
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
    stream = event_stream(
        "/api/import/preview",
        "POST",
        json={
            "track_ids": [their_track.id],
            "mine_collection_id": mine.id,
            "theirs_collection_id": theirs.id,
            "destination_root": f"  {destination}  ",
            "structure_mode": "flat",
            "upgrade_action": "keep_both",
        },
    )

    body = stream.done
    operation = body["operations"][0]
    assert operation["destination"] == os.path.normpath(str(destination / "song.mp3"))


def test_preview_with_upgrade(
    session, tmp_path, make_track, collections, destination, event_stream
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

    stream = event_stream(
        "/api/import/preview",
        "POST",
        json={
            "track_ids": [their_id],
            "mine_collection_id": mine.id,
            "theirs_collection_id": theirs.id,
            "destination_root": str(destination),
            "structure_mode": "flat",
            "upgrade_action": "keep_both",
        },
    )

    body = stream.done
    assert len(body["upgrades"]) == 1
    assert body["upgrades"][0]["mine"]["id"] == mine_id
    assert body["upgrades"][0]["theirs"]["id"] == their_id


def test_preview_already_have_track_is_rejected(
    session, tmp_path, make_track, collections, destination, event_stream
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

    stream = event_stream(
        "/api/import/preview",
        "POST",
        json={
            "track_ids": [their_id],
            "mine_collection_id": mine.id,
            "theirs_collection_id": theirs.id,
            "destination_root": str(destination),
            "structure_mode": "flat",
            "upgrade_action": "keep_both",
        },
    )

    assert title in stream.error["detail"]


def test_preview_reports_bytes_required_and_free(
    session, monkeypatch, make_track, collections, destination, event_stream, tmp_path
):
    def disk_usage_mock(path):
        return types.SimpleNamespace(total=9_999_999, used=1_111_111, free=8_888_888)

    monkeypatch.setattr(main.shutil, "disk_usage", disk_usage_mock)

    mine, theirs = collections

    their_track_1 = make_track(
        collection_id=theirs.id,
        file_path=str(tmp_path / "theirs" / "song_1.mp3"),
        file_size=3_333_333,
    )
    their_track_2 = make_track(
        collection_id=theirs.id,
        file_path=str(tmp_path / "theirs" / "song_2.mp3"),
        file_size=1_111_111,
    )
    session.add(their_track_1)
    session.add(their_track_2)
    session.commit()

    their_id_1 = their_track_1.id
    their_id_2 = their_track_2.id

    stream = event_stream(
        "/api/import/preview",
        "POST",
        json={
            "track_ids": [their_id_1, their_id_2],
            "mine_collection_id": mine.id,
            "theirs_collection_id": theirs.id,
            "destination_root": str(destination),
            "structure_mode": "flat",
            "upgrade_action": "keep_both",
        },
    )

    body = stream.done
    assert body["bytes_required"] == 4_444_444
    assert body["bytes_free"] == 8_888_888


def test_preview_counts_only_copies_toward_bytes_required(
    session, make_track, collections, destination, event_stream, tmp_path
):
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

    their_id = their_track.id

    stream = event_stream(
        "/api/import/preview",
        "POST",
        json={
            "track_ids": [their_id],
            "mine_collection_id": mine.id,
            "theirs_collection_id": theirs.id,
            "destination_root": str(destination),
            "structure_mode": "flat",
            "upgrade_action": "delete",
        },
    )

    body = stream.done
    assert body["bytes_required"] == 2_000_000


def test_bytes_required_normalizes_the_operation_source(make_track):
    # No session, no collections: the helper reads two attributes off a Track
    # and never touches the database. plan_copy carries file_path across to
    # source verbatim, so a row spelled with forward slashes or a dot segment
    # reaches the lookup unnormalized while the map keys are normalized.
    their_track = make_track(
        format="FLAC",
        file_path="D:/Music/./Song.mp3",
        file_size=2_222_222,
    )

    planned_operation = PlannedOperation(
        source="D:/Music/./Song.mp3",
        destination=r"D:\Import\Song.mp3",
        action=ActionType.COPY,
        group_id=1,
        overwrites=False,
    )

    assert main._bytes_required([planned_operation], [their_track]) == 2_222_222


def test_bytes_required_is_zero_when_nothing_is_copied():
    # Two shapes of "no copies". The second is the one that earns its place:
    # it passes no tracks at all, so the lookup would raise KeyError if the
    # copy filter ever stopped running before it.
    delete = PlannedOperation(
        source=r"C:\music\Radiohead\Creep.mp3",
        destination=None,
        action=ActionType.DELETE,
        group_id=1,
    )

    assert main._bytes_required([], []) == 0
    assert main._bytes_required([delete], []) == 0


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
    session, tmp_path, make_track, collections, destination, event_stream
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

    stream = event_stream(
        "/api/import/execute",
        "POST",
        json={
            "track_ids": [their_id],
            "mine_collection_id": mine.id,
            "theirs_collection_id": theirs.id,
            "destination_root": str(destination),
            "structure_mode": "flat",
            "upgrade_action": "keep_both",
        },
    )

    body = stream.done
    assert body["status_counts"]["success"] == 1
    assert body["status_counts"]["failed"] == 0
    assert body["operations"][0]["status"] == "success"
    assert (destination / "song.mp3").read_bytes() == b"audio data"


def test_execute_returns_status_counts(
    session, tmp_path, make_track, collections, destination, event_stream
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

    stream = event_stream(
        "/api/import/execute",
        "POST",
        json={
            "track_ids": [their_id],
            "mine_collection_id": mine.id,
            "theirs_collection_id": theirs.id,
            "destination_root": str(destination),
            "structure_mode": "flat",
            "upgrade_action": "keep_both",
        },
    )

    body = stream.done
    assert body["status_counts"]["success"] == 1
    assert body["status_counts"]["failed"] == 0
    assert body["status_counts"]["skipped"] == 0


def test_copied_files_get_no_track_rows(
    session, tmp_path, make_track, collections, destination, event_stream
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

    stream = event_stream(
        "/api/import/execute",
        "POST",
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

    # The done frame, not a status code: every stream answers 200, including
    # one carrying nothing but an error frame.
    assert stream.done["status_counts"] == {"success": 1, "failed": 0, "skipped": 0}
    assert (destination / "song.mp3").exists()

    # Imported files are deliberately not registered: destination_root can be
    # any folder, so nothing guarantees it sits inside mine's collection tree.
    # A re-scan is how they become visible.
    assert len(session.exec(select(Track)).all()) == tracks_before
    assert rows == []


def test_delete_action_removes_the_track_row(
    session, tmp_path, make_track, collections, destination, event_stream
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

    event_stream(
        "/api/import/execute",
        "POST",
        json={
            "track_ids": [their_id],
            "mine_collection_id": mine.id,
            "theirs_collection_id": theirs.id,
            "destination_root": str(destination),
            "structure_mode": "flat",
            "upgrade_action": "delete",
        },
    )

    assert (destination / "their_song.mp3").exists()
    assert not source_file_mine.exists()
    assert session.get(Track, mine_id) is None


def test_move_action_removes_the_track_row(
    session, tmp_path, make_track, collections, destination, event_stream
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

    event_stream(
        "/api/import/execute",
        "POST",
        json={
            "track_ids": [their_id],
            "mine_collection_id": mine.id,
            "theirs_collection_id": theirs.id,
            "destination_root": str(destination),
            "structure_mode": "flat",
            "upgrade_action": "move",
        },
    )

    assert (destination / "their_song.mp3").exists()
    assert (destination / "_superseded" / "mine_song.mp3").exists()
    assert session.get(Track, mine_id) is None


def test_keep_both_leaves_my_row_and_file(
    session, tmp_path, make_track, collections, destination, event_stream
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

    stream = event_stream(
        "/api/import/execute",
        "POST",
        json={
            "track_ids": [their_id],
            "mine_collection_id": mine.id,
            "theirs_collection_id": theirs.id,
            "destination_root": str(destination),
            "structure_mode": "flat",
            "upgrade_action": "keep_both",
        },
    )

    # keep_both plans a copy and nothing else, so one successful operation is
    # the whole plan. Asserting the counts rather than a status code: every
    # stream answers 200, so that told us nothing about whether it worked.
    assert stream.done["status_counts"] == {"success": 1, "failed": 0, "skipped": 0}
    assert (destination / "their_song.mp3").exists()
    assert source_file_mine.exists()
    assert not (destination / "_superseded" / "mine_song.mp3").exists()
    assert session.get(Track, mine_id) is not None


def test_failed_copy_returns_200_with_failed_status(
    session, tmp_path, make_track, collections, destination, event_stream
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

    stream = event_stream(
        "/api/import/execute",
        "POST",
        json={
            "track_ids": [their_id],
            "mine_collection_id": mine.id,
            "theirs_collection_id": theirs.id,
            "destination_root": str(destination),
            "structure_mode": "flat",
            "upgrade_action": "keep_both",
        },
    )

    assert not (destination / "their_song.mp3").exists()
    body = stream.done
    assert body["status_counts"]["success"] == 0
    assert body["status_counts"]["failed"] == 1
    assert body["status_counts"]["skipped"] == 0


def test_failed_copy_skips_the_delete_and_keeps_my_file(
    session, tmp_path, make_track, collections, destination, event_stream
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

    stream = event_stream(
        "/api/import/execute",
        "POST",
        json={
            "track_ids": [their_id],
            "mine_collection_id": mine.id,
            "theirs_collection_id": theirs.id,
            "destination_root": str(destination),
            "structure_mode": "flat",
            "upgrade_action": "delete",
        },
    )

    assert not (destination / "their_song.mp3").exists()
    assert source_file_mine.exists()
    body = stream.done
    assert body["status_counts"]["success"] == 0
    assert body["status_counts"]["failed"] == 1
    assert body["status_counts"]["skipped"] == 1
    assert session.get(Track, mine_id) is not None


def test_one_failed_group_does_not_stop_another(
    session, tmp_path, make_track, collections, destination, event_stream
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

    stream = event_stream(
        "/api/import/execute",
        "POST",
        json={
            "track_ids": [their_id_g0, their_id_g1],
            "mine_collection_id": mine.id,
            "theirs_collection_id": theirs.id,
            "destination_root": str(destination),
            "structure_mode": "flat",
            "upgrade_action": "delete",
        },
    )

    assert not (destination / "their_song_g0.mp3").exists()
    assert (destination / "their_song_g1.mp3").exists()
    assert source_file_mine_g0.exists()
    assert not source_file_mine_g1.exists()
    body = stream.done
    assert body["status_counts"]["success"] == 2
    assert body["status_counts"]["failed"] == 1
    assert body["status_counts"]["skipped"] == 1
    assert session.get(Track, mine_id_g0) is not None
    assert session.get(Track, mine_id_g1) is None


def test_log_file_is_written_to_destination_root(
    session, tmp_path, make_track, collections, destination, event_stream
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

    stream = event_stream(
        "/api/import/execute",
        "POST",
        json={
            "track_ids": [their_id],
            "mine_collection_id": mine.id,
            "theirs_collection_id": theirs.id,
            "destination_root": str(destination),
            "structure_mode": "flat",
            "upgrade_action": "keep_both",
        },
    )

    body = stream.done
    assert body["log_error"] is None

    logs = list(destination.glob("import_log_*.json"))
    assert len(logs) == 1

    entries = json.loads(logs[0].read_text())
    assert len(entries) == 1
    assert entries[0]["status"] == "success"
    assert entries[0]["operation"]["action"] == "copy"

    assert body["log_path"] == str(logs[0])


def test_execute_rejects_a_non_candidate_id(
    session, tmp_path, make_track, collections, destination, event_stream
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

    stream = event_stream(
        "/api/import/execute",
        "POST",
        json={
            "track_ids": [their_id],
            "mine_collection_id": mine.id,
            "theirs_collection_id": theirs.id,
            "destination_root": str(destination),
            "structure_mode": "flat",
            "upgrade_action": "keep_both",
        },
    )

    assert title in stream.error["detail"]

    # Nothing ran: validation happens before any file is touched.
    assert list(destination.iterdir()) == []


def test_diff_buckets_a_missing_track(
    event_stream, session, tmp_path, make_track, collections
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

    stream = event_stream(f"/api/diff?mine={mine.id}&theirs={theirs.id}", "GET")

    body = stream.done
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


def test_the_diff_endpoint_reports_a_rejection(
    event_stream, make_track, collections, session, tmp_path
):
    # The rejection has to reach the browser or it may as well not exist: on
    # screen a rejected track is otherwise identical to one you never owned.
    # This is the only test that the new list survives the schema layer.
    #
    # Uniform frames give an error rate that is arithmetic — 5 bits per frame
    # is 5/32 = 0.15625, just over the 0.15 threshold — so the rejection is a
    # certainty rather than a property of two random seeds.
    mine, theirs = collections
    session.add(
        make_track(
            collection_id=mine.id,
            format="MP3",
            duration=200,
            file_size=1_000_000,
            file_path=str(tmp_path / "mine" / "near.mp3"),
            file_name="near.mp3",
            fingerprint=pack_fingerprint([0b11111] * 200),
            fingerprint_length=FPCALC_LENGTH_SECONDS,
            fingerprint_algorithm=FPCALC_ALGORITHM,
        )
    )
    session.add(
        make_track(
            collection_id=theirs.id,
            format="FLAC",
            duration=201,
            file_size=4_000_000,
            file_path=str(tmp_path / "theirs" / "quiet.flac"),
            file_name="quiet.flac",
            fingerprint=pack_fingerprint([0] * 200),
            fingerprint_length=FPCALC_LENGTH_SECONDS,
            fingerprint_algorithm=FPCALC_ALGORITHM,
        )
    )
    session.commit()

    stream = event_stream(f"/api/diff?mine={mine.id}&theirs={theirs.id}", "GET")

    # The done frame, never the status code: every stream answers 200,
    # including one whose whole body is an error frame.
    results = stream.done["match_results"]
    (rejection,) = results["rejected"]
    assert rejection["theirs"]["file_name"] == "quiet.flac"
    assert rejection["mine"]["file_name"] == "near.mp3"
    assert rejection["error_rate"] == pytest.approx(5 / 32)
    # And it is still a missing track, so every existing consumer of that
    # bucket keeps working unchanged.
    assert [t["file_name"] for t in results["missing"]] == ["quiet.flac"]
    # The other half of test_a_diff_without_fpcalc_says_so. That test catches
    # a flag stuck at True; this one catches a flag stuck at False, which
    # would show the warning on every diff.
    assert results["fingerprints_available"] is True


def test_the_diff_endpoint_stores_the_fingerprints_it_computed(
    event_stream,
    make_track,
    monkeypatch,
    collections,
    session,
    fake_fingerprint,
    tmp_path,
):
    # The parameter is a file path, not a track: compute_fingerprint is called
    # as compute_fingerprint(track.file_path). Every path gets the same answer,
    # so the lambda ignores it and exists only to absorb the argument.
    #
    # matching.compute_fingerprint, not fingerprinting's. matching.py imported
    # the name into its own namespace, so patching the original would leave
    # that reference alone and the real fpcalc would run.
    monkeypatch.setattr(
        "matching.compute_fingerprint", lambda path: fake_fingerprint(7, 200)
    )
    mine, theirs = collections

    mine_track_1 = make_track(
        duration=200,
        file_size=1_000_000,
        file_path=str(tmp_path / "mine" / "song_1.mp3"),
        collection_id=mine.id,
        file_hash="hash1",
    )
    mine_track_2 = make_track(
        duration=200,
        file_size=3_000_000,
        file_path=str(tmp_path / "mine" / "song_2.mp3"),
        collection_id=mine.id,
        file_hash="hash2",
    )
    theirs_track_1 = make_track(
        duration=200,
        file_size=1_000_000,
        file_path=str(tmp_path / "theirs" / "song_1.mp3"),
        collection_id=theirs.id,
        file_hash="hash3",
    )
    theirs_track_2 = make_track(
        duration=200,
        file_size=4_000_000,
        file_path=str(tmp_path / "theirs" / "song_2.mp3"),
        collection_id=theirs.id,
        file_hash="hash4",
    )
    session.add(mine_track_1)
    session.add(mine_track_2)
    session.add(theirs_track_1)
    session.add(theirs_track_2)
    session.commit()

    stream = event_stream(f"/api/diff?mine={mine.id}&theirs={theirs.id}", "GET")

    assert stream.events[-1] == "done"
    rows = session.exec(select(Track)).all()
    for row in rows:
        assert row.fingerprint is not None


def test_a_diff_without_fpcalc_says_so(
    event_stream, session, tmp_path, make_track, collections, monkeypatch
):
    # Overrides the autouse fpcalc_is_installed, because this patch runs later.
    monkeypatch.setattr("main.fpcalc_available", lambda: False)
    mine, theirs = collections

    their_track = make_track(
        file_path=str(tmp_path / "theirs" / "song.mp3"),
        collection_id=theirs.id,
        file_size=1_000_000,
        title="Only Theirs",
    )
    session.add(their_track)
    session.commit()

    stream = event_stream(f"/api/diff?mine={mine.id}&theirs={theirs.id}", "GET")

    assert stream.done["match_results"]["fingerprints_available"] is False


def test_the_diff_lists_the_files_it_could_not_read(
    collections, make_track, tmp_path, event_stream, session
):
    mine, theirs = collections

    my_track = make_track(
        file_path=str(tmp_path / "mine" / "song.mp3"),
        collection_id=mine.id,
        file_size=1_000_000,
    )
    their_track = make_track(
        file_path=str(tmp_path / "theirs" / "song.mp3"),
        collection_id=theirs.id,
        file_size=1_000_000,
    )
    session.add(my_track)
    session.add(their_track)
    session.commit()

    stream = event_stream(f"/api/diff?mine={mine.id}&theirs={theirs.id}", "GET")

    assert stream.done["match_results"]["unreadable_files"] == [their_track.file_path]


def test_scan_returns_collection_and_stats(event_stream, tmp_path, fixtures_dir):
    shutil.copy(fixtures_dir / "test_track.mp3", tmp_path / "test_track.mp3")

    stream = event_stream(
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
    client, event_stream, tmp_path, fixtures_dir
):
    shutil.copy(fixtures_dir / "test_track.mp3", tmp_path / "test_track.mp3")

    event_stream(
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
    client, event_stream, tmp_path, fixtures_dir
):
    shutil.copy(fixtures_dir / "test_track.mp3", tmp_path / "test_track.mp3")

    event_stream(
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
    event_stream, tmp_path, fixtures_dir
):
    shutil.copy(fixtures_dir / "test_track.mp3", tmp_path / "test_track.mp3")

    # A path pasted from Explorer or a chat message routinely carries a
    # leading or trailing space. normpath does not strip whitespace, so
    # without the validator's strip() the padded string reaches isdir and
    # the request 400s on a directory that plainly exists.
    stream = event_stream(
        "/api/collections/scan",
        json={"root_path": f"  {tmp_path}  ", "name": "Padded"},
    )

    body = stream.done
    assert body["added"] == 1
    assert body["collection"]["root_path"] == os.path.normpath(str(tmp_path))


def test_rescan_returns_collection_and_stats(event_stream, tmp_path, fixtures_dir):
    shutil.copy(fixtures_dir / "test_track.mp3", tmp_path / "test_track.mp3")

    first = event_stream(
        "/api/collections/scan",
        json={"root_path": str(tmp_path), "name": "Theirs"},
    )
    collection_id = first.done["collection"]["id"]

    body = event_stream(f"/api/collections/{collection_id}/rescan").done
    assert body["scanned"] == 1
    assert body["added"] == 0
    assert body["updated"] == 0
    assert body["deleted"] == 0


def test_rescan_unknown_collection_returns_404(client):
    response = client.post("/api/collections/99999/rescan")
    assert response.status_code == 404
    assert "Collection not found" in response.json()["detail"]


def test_rescan_triggers_deletion(event_stream, tmp_path, fixtures_dir):
    shutil.copy(fixtures_dir / "test_track.mp3", tmp_path / "test_track.mp3")

    first = event_stream(
        "/api/collections/scan",
        json={"root_path": str(tmp_path), "name": "Theirs"},
    )
    collection_id = first.done["collection"]["id"]

    os.remove(tmp_path / "test_track.mp3")

    body = event_stream(f"/api/collections/{collection_id}/rescan").done
    assert body["scanned"] == 0
    assert body["added"] == 0
    assert body["updated"] == 0
    assert body["deleted"] == 1


def test_rescan_nonexistent_root_returns_400(
    client, event_stream, tmp_path, fixtures_dir
):
    shutil.copy(fixtures_dir / "test_track.mp3", tmp_path / "test_track.mp3")

    first = event_stream(
        "/api/collections/scan",
        json={"root_path": str(tmp_path), "name": "Theirs"},
    )
    collection_id = first.done["collection"]["id"]

    # Simulate the collection root being unmounted or deleted.
    shutil.rmtree(tmp_path)

    response2 = client.post(f"/api/collections/{collection_id}/rescan")
    assert response2.status_code == 400
    assert "not found" in response2.json()["detail"]


def test_event_stream_ends_with_a_done_frame(event_stream, tmp_path, fixtures_dir):
    shutil.copy(fixtures_dir / "test_track.mp3", tmp_path / "test_track.mp3")

    stream = event_stream(
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


def test_event_stream_reports_progress_frames(event_stream, monkeypatch, tmp_path):
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

    stream = event_stream(
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


# The next two call the adapters directly rather than reading an import
# stream. A phase assertion made over a real stream would need the poll
# interval shrunk and the work slowed, as above, and would then be timing
# dependent for a claim that has nothing to do with timing. These are pure
# functions: a callback in, a callback out.
#
# The phase is the reason they exist. Mislabelling the copy phase leaves the
# UI saying "nothing on disk has changed yet" for the whole of the part where
# it is being changed, and every other assertion in this file still passes.
def test_comparing_reporter_labels_the_phase_and_maps_the_counts():
    seen = []

    report = main._comparing_reporter(seen.append)
    report(
        DiffProgress(
            theirs_processed_count=111,
            theirs_count=3500,
            hashed_count=7,
            fingerprinted_count=3,
            current_path=r"C:\music\Radiohead\Creep.mp3",
        )
    )

    # hashed_count has nowhere to go, and that is the adaptation: the stream
    # carries one shape for both phases, and a copy has nothing to hash.
    assert seen == [
        main.ImportProgress(
            phase=ImportPhase.COMPARING,
            processed_count=111,
            total_count=3500,
            current_path=r"C:\music\Radiohead\Creep.mp3",
        )
    ]


def test_copying_reporter_labels_the_phase_and_maps_the_counts():
    seen = []

    report = main._copying_reporter(seen.append)
    report(
        ExecuteProgress(
            operations_processed_count=11,
            operations_count=42,
            current_path=r"C:\music\Radiohead\Creep.mp3",
        )
    )

    # The two counts are deliberately unequal and unlike the ones above: this
    # asserts the whole object, so crossing processed with total, or carrying
    # the comparing phase's totals into this one, both fail here.
    assert seen == [
        main.ImportProgress(
            phase=ImportPhase.COPYING,
            processed_count=11,
            total_count=42,
            current_path=r"C:\music\Radiohead\Creep.mp3",
        )
    ]


def test_event_stream_reports_a_scan_failure_as_an_error_frame(
    event_stream, monkeypatch, caplog, tmp_path
):
    def exploding_scan(root_path, collection_id, session, on_progress=None):
        raise OSError("the drive went away")

    monkeypatch.setattr(main, "scan_folder", exploding_scan)

    stream = event_stream(
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
    event_stream, session, tmp_path, fixtures_dir
):
    shutil.copy(fixtures_dir / "test_track.mp3", tmp_path / "test_track.mp3")

    first = event_stream(
        "/api/collections/scan",
        json={"root_path": str(tmp_path), "name": "Theirs"},
    )
    collection_id = first.done["collection"]["id"]
    session.expire_all()
    before = session.get(Collection, collection_id).last_scanned_at
    assert before is not None

    event_stream(f"/api/collections/{collection_id}/rescan")

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
    collections, destination, make_ambiguity, event_stream
):
    mine, theirs = collections
    ambiguity = make_ambiguity()
    their_track = ambiguity.theirs[0]

    stream = event_stream(
        "/api/import/preview",
        "POST",
        json=_import_body(mine, theirs, destination, [their_track.id]),
    )

    detail = stream.error["detail"]
    # Names the track and says what to do, rather than just refusing: this is
    # the message a user sees for every unresolved review row.
    assert "Not import candidates" in detail
    assert their_track.file_name in detail
    assert "run Compare again" in detail


def test_resolution_none_of_these_routes_to_missing(
    collections, destination, make_ambiguity, event_stream
):
    mine, theirs = collections
    ambiguity = make_ambiguity()
    their_track = ambiguity.theirs[0]

    stream = event_stream(
        "/api/import/preview",
        "POST",
        json=_import_body(
            mine,
            theirs,
            destination,
            [their_track.id],
            resolutions=[{"theirs_id": their_track.id, "mine_id": None}],
        ),
    )

    body = stream.done
    assert len(body["operations"]) == 1
    assert body["operations"][0]["action"] == "copy"
    assert body["operations"][0]["source"] == their_track.file_path
    # The point of "none of these": routed to missing, not paired with either
    # candidate. Without this the test passes even on a wrong pairing, since
    # an upgrade also produces a copy.
    assert body["upgrades"] == []


def test_resolution_deletes_the_chosen_file_only(
    collections, destination, make_ambiguity, event_stream
):
    mine, theirs = collections
    ambiguity = make_ambiguity(theirs_format="FLAC", mine_format="MP3")
    their_track = ambiguity.theirs[0]
    chosen, not_chosen = ambiguity.candidates

    stream = event_stream(
        "/api/import/preview",
        "POST",
        json=_import_body(
            mine,
            theirs,
            destination,
            [their_track.id],
            resolutions=[{"theirs_id": their_track.id, "mine_id": chosen.id}],
            upgrade_action="delete",
        ),
    )

    body = stream.done
    # Copy first, then the destructive step: the order is the safety
    # mechanism, not a formatting detail (§5b).
    assert [op["action"] for op in body["operations"]] == ["copy", "delete"]
    assert body["operations"][0]["source"] == their_track.file_path
    assert body["operations"][1]["source"] == chosen.file_path
    assert not_chosen.file_path not in {op["source"] for op in body["operations"]}


def test_resolution_naming_a_file_that_is_not_a_candidate_is_rejected(
    session,
    tmp_path,
    make_track,
    collections,
    destination,
    make_ambiguity,
    event_stream,
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

    stream = event_stream(
        "/api/import/preview",
        "POST",
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
    detail = stream.error["detail"]
    assert unrelated.file_name in detail
    assert their_track.file_name in detail
    assert "not one of the files matched" in detail


def test_two_resolutions_claiming_the_same_file_are_rejected(
    collections, destination, make_ambiguity, event_stream
):
    mine, theirs = collections
    # Two tracks of theirs sharing one candidate set, so both can name the
    # same file of mine. FLAC over MP3 so both classify as upgrades and
    # actually reach the double-booking check.
    ambiguity = make_ambiguity(theirs_format="FLAC", mine_format="MP3", theirs_count=2)
    first, second = ambiguity.theirs
    contested = ambiguity.candidates[0]

    stream = event_stream(
        "/api/import/preview",
        "POST",
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

    detail = stream.error["detail"]
    # Both tracks of theirs share artist and title — that is why they matched
    # the same file — so the message has to name them by file to be usable.
    # Pins which check fired: several other conditions also return 400, so a
    # bare status assertion would pass on the wrong rejection.
    assert "would both replace" in detail
    assert first.file_name in detail
    assert second.file_name in detail
    assert contested.file_name in detail


def test_resolution_to_a_better_file_of_mine_is_rejected(
    collections, destination, make_ambiguity, event_stream
):
    mine, theirs = collections
    # Theirs is the lossy one, so either candidate of mine wins on quality.
    ambiguity = make_ambiguity(theirs_format="MP3", mine_format="FLAC")
    their_track = ambiguity.theirs[0]
    chosen = ambiguity.candidates[0]

    stream = event_stream(
        "/api/import/preview",
        "POST",
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
    detail = stream.error["detail"]
    assert "Nothing to import" in detail
    assert their_track.file_name in detail


def test_diff_stream_ends_with_a_done_frame(
    event_stream, tmp_path, collections, session, make_track
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

    stream = event_stream(f"/api/diff?mine={mine.id}&theirs={theirs.id}", "GET")

    assert stream.events[-1] == "done"
    assert set(stream.events[:-1]) <= {"progress"}
    assert stream.events.count("done") == 1
    assert stream.error is None


def test_diff_stream_reports_progress_frames(event_stream, monkeypatch, collections):
    monkeypatch.setattr(main, "PROGRESS_INTERVAL_SECONDS", 0.001)
    mine, theirs = collections

    def slow_match(
        tracks_mine,
        tracks_theirs,
        on_progress=None,
        fingerprints_available=True,
        format_ranks=None,
    ):
        on_progress(
            # One of three, not three of three: a fake that claims to be
            # finished while it is still running is a small lie for the next
            # person to copy out of this file.
            DiffProgress(
                theirs_processed_count=1,
                theirs_count=3,
                hashed_count=0,
                fingerprinted_count=0,
                current_path=r"C:\music\Radiohead\Creep.mp3",
            )
        )
        time.sleep(0.3)
        return MatchResult()

    monkeypatch.setattr(main, "match_collections", slow_match)

    stream = event_stream(f"/api/diff?mine={mine.id}&theirs={theirs.id}", "GET")

    assert stream.progress
    assert stream.progress[-1] == {
        "theirs_processed_count": 1,
        "theirs_count": 3,
        "hashed_count": 0,
        "fingerprinted_count": 0,
        "current_path": r"C:\music\Radiohead\Creep.mp3",
    }


def test_diff_stream_reports_a_failure_as_an_error_frame(
    event_stream, monkeypatch, caplog, collections
):
    mine, theirs = collections

    def exploding_match(
        tracks_mine,
        tracks_theirs,
        on_progress=None,
        fingerprints_available=True,
        format_ranks=None,
    ):
        raise OSError("the drive went away")

    monkeypatch.setattr(main, "match_collections", exploding_match)

    stream = event_stream(f"/api/diff?mine={mine.id}&theirs={theirs.id}", "GET")

    assert stream.done is None
    assert stream.events[-1] == "error"
    assert stream.error == {"detail": "the drive went away"}
    assert "Diff of" in caplog.text
    assert "OSError" in caplog.text


def test_diff_stream_survives_a_failure_before_the_collections_load(
    event_stream, monkeypatch, caplog, collections
):
    mine, theirs = collections
    real_load_collections = main._load_collections
    calls = []

    # _load_collections runs twice per diff: once on the request thread to
    # validate, and again inside the worker with its own session. This fake
    # lets the first through and fails the second, which is the real race —
    # another client deletes the collection in between.
    def load_then_vanish(session, mine_id, theirs_id):
        calls.append((mine_id, theirs_id))
        if len(calls) == 1:
            return real_load_collections(session, mine_id, theirs_id)
        raise HTTPException(status_code=404, detail="Collection not found.")

    monkeypatch.setattr(main, "_load_collections", load_then_vanish)

    stream = event_stream(f"/api/diff?mine={mine.id}&theirs={theirs.id}", "GET")

    # Two calls, so the worker really did load again rather than reuse the
    # request's objects. That reload is what keeps the ORM objects inside one
    # thread and one session.
    assert len(calls) == 2
    assert stream.done is None
    assert stream.error == {"detail": "404: Collection not found."}
    # The failure happens before either collection is bound. An error handler
    # that named them instead of their ids would raise UnboundLocalError here,
    # replace the real failure, and escape the worker entirely — after 200 had
    # already gone out.
    assert "Diff of" in caplog.text


def test_diff_validation_failure_never_opens_a_stream(client, collections):
    mine, theirs = collections

    self_comparison = client.get(f"/api/diff?mine={mine.id}&theirs={mine.id}")
    unknown_collection = client.get(f"/api/diff?mine={mine.id}&theirs=99999")

    # Both guards run before the StreamingResponse is returned, so a bad
    # request still gets a real status and a JSON detail. If either ever moves
    # after the stream opens it becomes a 200 event-stream, and
    # throwForResponse in api.ts stops seeing the failure at all.
    for response, status in ((self_comparison, 400), (unknown_collection, 404)):
        assert response.status_code == status
        assert response.headers["content-type"].startswith("application/json")


def _format_order_body(client):
    response = client.get("/api/settings/format-order")
    assert response.status_code == 200
    return response.json()


def _reordered_tiers():
    """The default order with its tiers swapped, which the rules still allow."""
    return main.default_tiers()[::-1]


def _split_tiers():
    """The default order with its first tier split in two: three tiers, all legal."""
    lossless, lossy = main.default_tiers()
    return [[lossless[0]], lossless[1:], lossy]


def test_format_order_is_the_default_when_nothing_is_saved(client):
    body = _format_order_body(client)
    assert body["tiers"] == main.default_tiers()
    assert body["placed"] == []
    assert body["updated_at"] is None
    assert "MP3" in body["lossy_formats"]
    assert "FLAC" not in body["lossy_formats"]


def test_put_format_order_is_read_back(client):
    order = _reordered_tiers()
    assert (
        client.put("/api/settings/format-order", json={"tiers": order}).status_code
        == 200
    )
    body = _format_order_body(client)
    assert body["tiers"] == order
    assert body["updated_at"] is not None


def test_put_the_default_order_saves_no_rows(client, session):
    assert (
        client.put(
            "/api/settings/format-order", json={"tiers": main.default_tiers()}
        ).status_code
        == 200
    )
    assert session.exec(select(FormatOrderRow)).all() == []
    assert _format_order_body(client)["updated_at"] is None


def test_put_replaces_the_whole_order(client, session):
    # Two complete orders that name the same formats, which is what every
    # second PUT does: the rows of the first must be gone, and their formats
    # must be writable again in the same request.
    first = _split_tiers()
    second = _reordered_tiers()

    assert (
        client.put("/api/settings/format-order", json={"tiers": first}).status_code
        == 200
    )
    assert (
        client.put("/api/settings/format-order", json={"tiers": second}).status_code
        == 200
    )

    assert len(session.exec(select(FormatOrderRow)).all()) == len(
        [name for tier in second for name in tier]
    )
    assert _format_order_body(client)["tiers"] == second


# Each order has the shape the schema asks for, so every one of them reaches
# validate_tiers. A list of strings instead of a list of tiers would be turned
# away by pydantic with 422, and would test nothing about the rules.
@pytest.mark.parametrize(
    "bad, expected",
    [
        ([["FLAC", "MP3"]], "MP3"),
        ([["MP3"]], "FLAC"),
        ([*main.default_tiers(), ["NOT_A_FORMAT"]], "NOT_A_FORMAT"),
    ],
    ids=["mixed tier", "missing formats", "unknown format"],
)
def test_put_rejects_a_bad_order(client, bad, expected):
    response = client.put("/api/settings/format-order", json={"tiers": bad})

    assert response.status_code == 400
    # The message names the format at fault, because the editor shows it to
    # the user, who has to know which chip to move.
    assert expected in response.json()["detail"]


def test_a_format_missing_from_the_saved_order_is_listed_as_placed(client, session):
    # A saved order that is not the default, because a PUT of the default
    # saves no rows and there would be nothing to delete. Removing one row is
    # the state a new format arrives in: every other format is ranked, and
    # this one has never been.
    client.put("/api/settings/format-order", json={"tiers": _reordered_tiers()})
    session.delete(session.get(FormatOrderRow, "FLAC"))
    session.commit()

    body = _format_order_body(client)

    assert body["placed"] == ["FLAC"]
    assert any("FLAC" in tier for tier in body["tiers"])


def test_the_diff_uses_the_saved_format_order(
    client, session, tmp_path, make_track, collections, event_stream
):
    # One FLAC of mine against one MP3 of theirs: an upgrade only while MP3
    # outranks FLAC, which is what the saved order below says and the default
    # order does not. The file sizes differ, so the hash tier stays out of it,
    # and the tags and durations match, so the tag tier pairs the two.
    mine, theirs = collections
    session.add(
        make_track(
            collection_id=mine.id,
            format="FLAC",
            file_path=str(tmp_path / "mine" / "song.flac"),
            file_size=4_000_000,
        )
    )
    session.add(
        make_track(
            collection_id=theirs.id,
            format="MP3",
            file_path=str(tmp_path / "theirs" / "song.mp3"),
            file_size=1_000_000,
        )
    )
    session.commit()
    client.put("/api/settings/format-order", json={"tiers": _reordered_tiers()})

    stream = event_stream(f"/api/diff?mine={mine.id}&theirs={theirs.id}", "GET")

    assert stream.done["match_counts"]["upgrade_available"] == 1


def _saved_order_pair(session, tmp_path, make_track, collections):
    """One FLAC of mine and one MP3 of theirs, paired by their tags."""
    mine, theirs = collections
    session.add(
        make_track(
            collection_id=mine.id,
            format="FLAC",
            file_path=str(tmp_path / "mine" / "song.flac"),
            file_size=4_000_000,
        )
    )
    their_track = make_track(
        collection_id=theirs.id,
        format="MP3",
        file_path=str(tmp_path / "theirs" / "song.mp3"),
        file_size=1_000_000,
    )
    session.add(their_track)
    session.commit()
    return their_track


def test_the_import_recompute_uses_the_saved_format_order(
    client, session, tmp_path, make_track, collections, destination, event_stream
):
    # The import classifies again on the server before it plans, and that is
    # the pass that decides a deletion. Under the default order this track is
    # already_have, and the request is refused as not an import candidate.
    mine, theirs = collections
    their_track = _saved_order_pair(session, tmp_path, make_track, collections)
    client.put("/api/settings/format-order", json={"tiers": _reordered_tiers()})

    stream = event_stream(
        "/api/import/preview",
        "POST",
        json=_import_body(mine, theirs, destination, [their_track.id]),
    )

    assert stream.error is None
    assert len(stream.done["upgrades"]) == 1


def test_a_format_placed_after_its_row_vanished_is_ranked_in_a_diff(
    client, session, tmp_path, make_track, collections, event_stream
):
    # The state a format added by an update arrives in: every other format has
    # a saved row and this one has none. effective_tiers places it, so it must
    # rank where the editor shows it. Ranked from the rows alone it would
    # score 0, below every format, and their MP3 would lose to my FLAC.
    mine, theirs = collections
    _saved_order_pair(session, tmp_path, make_track, collections)
    client.put("/api/settings/format-order", json={"tiers": _reordered_tiers()})
    session.delete(session.get(FormatOrderRow, "MP3"))
    session.commit()

    stream = event_stream(f"/api/diff?mine={mine.id}&theirs={theirs.id}", "GET")

    assert stream.done["match_counts"]["upgrade_available"] == 1


def test_a_review_answer_uses_the_saved_format_order(
    client, collections, destination, make_ambiguity, event_stream
):
    # The other place the server classifies a pairing: the answer to a review,
    # judged by classify_pairing itself rather than by the matcher. Under the
    # default order this request answers 400, because the file chosen is at
    # least as good as theirs.
    mine, theirs = collections
    ambiguity = make_ambiguity(theirs_format="MP3", mine_format="FLAC")
    their_track = ambiguity.theirs[0]
    chosen = ambiguity.candidates[0]
    client.put("/api/settings/format-order", json={"tiers": _reordered_tiers()})

    stream = event_stream(
        "/api/import/preview",
        "POST",
        json=_import_body(
            mine,
            theirs,
            destination,
            [their_track.id],
            resolutions=[{"theirs_id": their_track.id, "mine_id": chosen.id}],
        ),
    )

    assert stream.error is None
    assert len(stream.done["upgrades"]) == 1


def test_a_rejected_put_leaves_the_saved_order_alone(client):
    order = _reordered_tiers()
    client.put("/api/settings/format-order", json={"tiers": order})

    response = client.put(
        "/api/settings/format-order", json={"tiers": [["FLAC", "MP3"]]}
    )

    assert response.status_code == 400
    assert _format_order_body(client)["tiers"] == order


def test_the_dev_origin_passes_a_preflight(client):
    origin = "http://localhost:5173"

    response = client.options(
        "/api/collections",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


def test_an_unlisted_origin_fails_a_preflight(client):
    response = client.options(
        "/api/collections",
        headers={
            "Origin": "http://example.test",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
