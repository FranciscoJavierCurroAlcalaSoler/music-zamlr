# tests/test_scanner.py
import os
import shutil

import mutagen
from sqlmodel import select

import scanner
from fingerprinting import FPCALC_ALGORITHM, FPCALC_LENGTH_SECONDS, pack_fingerprint
from importing import SUPERSEDED_DIR_NAME
from models import Collection, Track
from scanner import read_track, scan_folder, track_number_from_tag, year_from_date


def test_read_track_mp3(test_collection, fixtures_dir):
    track = read_track(
        str(fixtures_dir / "test_track.mp3"), collection_id=test_collection
    )

    assert track is not None
    assert track.file_name == "test_track.mp3"
    assert track.title == "Test Track MP3"
    assert track.artist == "Music Zamlr Fixtures"
    assert track.album == "Synthetic Test Album"
    assert track.track_number is None
    assert track.year == 2026
    assert track.format == "MP3"
    assert track.bit_depth is None
    assert track.bit_rate == 320000
    assert track.sample_rate == 44100
    assert track.duration == 5
    assert track.file_size == 206805
    assert track.file_hash is None
    assert track.collection_id == test_collection


def test_read_track_flac(test_collection, fixtures_dir):
    track = read_track(
        str(fixtures_dir / "test_track.flac"), collection_id=test_collection
    )

    assert track is not None
    assert track.file_name == "test_track.flac"
    assert track.title == "Test Track FLAC"
    assert track.artist == "Music Zamlr Fixture"
    assert track.album == "Synthetic Test Album"
    assert track.track_number is None
    assert track.year == 2026
    assert track.format == "FLAC"
    assert track.bit_depth == 16
    assert track.bit_rate == 112412
    assert track.sample_rate == 48000
    assert track.duration == 5
    assert track.file_size == 78544
    assert track.file_hash is None
    assert track.collection_id == test_collection


def test_read_track_nonexistent_file_returns_none(test_collection, fixtures_dir):
    track = read_track(
        str(fixtures_dir / "does_not_exist.mp3"), collection_id=test_collection
    )
    assert track is None


def test_year_from_date_handles_bare_year():
    assert year_from_date("2026") == 2026


def test_year_from_date_handles_full_date():
    assert year_from_date("2026-01-01") == 2026


def test_year_from_date_handles_none():
    assert year_from_date(None) is None


def test_track_number_from_tag_handles_fraction_format():
    assert track_number_from_tag("3/12") == 3


def test_track_number_from_tag_handles_empty_string():
    assert track_number_from_tag("") is None


def test_track_number_from_tag_handles_none():
    assert track_number_from_tag(None) is None


def test_scan_folder_finds_and_stores_audio_files(
    tmp_path, test_collection, session, fixtures_dir
):
    shutil.copy(fixtures_dir / "test_track.mp3", tmp_path / "test_track.mp3")
    shutil.copy(fixtures_dir / "test_track.flac", tmp_path / "test_track.flac")
    (tmp_path / "cover.jpg").write_text("not audio")

    result = scan_folder(str(tmp_path), collection_id=test_collection, session=session)

    assert result.scanned == 3
    assert result.added == 2
    assert result.skipped_non_audio == 1
    assert result.unreadable_files == []

    tracks = session.exec(select(Track)).all()
    assert len(tracks) == 2
    titles = {t.title for t in tracks}
    assert titles == {"Test Track MP3", "Test Track FLAC"}


def test_scan_folder_commits_its_work(tmp_path, test_collection, session, fixtures_dir):
    shutil.copy(fixtures_dir / "test_track.mp3", tmp_path / "test_track.mp3")

    scan_folder(str(tmp_path), collection_id=test_collection, session=session)

    # scan_folder commits a session it does not own, and nothing downstream
    # commits for it: get_session yields and closes without one. Drop that
    # commit and every other test here still passes — they read through the
    # same open transaction — while production silently loses every scan.
    # The rollback is what separates the two: a committed write survives it,
    # a merely flushed one does not. Not dead code; it is the assertion.
    session.rollback()

    assert session.exec(select(Track)).one().file_name == "test_track.mp3"
    assert session.get(Collection, test_collection).last_scanned_at is not None


def test_scan_folder_handles_uppercase_extensions(
    tmp_path, test_collection, session, fixtures_dir
):
    shutil.copy(fixtures_dir / "test_track.mp3", tmp_path / "TEST_UPPER.MP3")

    result = scan_folder(str(tmp_path), collection_id=test_collection, session=session)

    assert result.added == 1
    assert result.skipped_non_audio == 0


def test_scan_folder_batches_correctly(
    tmp_path, test_collection, monkeypatch, session, fixtures_dir
):
    monkeypatch.setattr("scanner.BATCH_SIZE", 1)

    shutil.copy(fixtures_dir / "test_track.mp3", tmp_path / "one.mp3")
    shutil.copy(fixtures_dir / "test_track.flac", tmp_path / "two.flac")

    result = scan_folder(str(tmp_path), collection_id=test_collection, session=session)

    assert result.added == 2
    tracks = session.exec(select(Track)).all()
    assert len(tracks) == 2


def test_scan_unchanged_folder_twice_does_not_raise(
    tmp_path, test_collection, session, fixtures_dir
):
    shutil.copy(fixtures_dir / "test_track.mp3", tmp_path / "test_track.mp3")

    result1 = scan_folder(str(tmp_path), collection_id=test_collection, session=session)
    result2 = scan_folder(str(tmp_path), collection_id=test_collection, session=session)

    assert result1.added == 1
    assert result2.added == 0


def test_scan_folder_removes_deleted_tracks_from_collection(
    tmp_path, test_collection, session, fixtures_dir
):
    shutil.copy(fixtures_dir / "test_track.mp3", tmp_path / "test_track.mp3")
    shutil.copy(fixtures_dir / "test_track.flac", tmp_path / "test_track.flac")

    scan_folder(str(tmp_path), collection_id=test_collection, session=session)

    (tmp_path / "test_track.flac").unlink()

    result = scan_folder(str(tmp_path), collection_id=test_collection, session=session)

    assert result.deleted == 1
    tracks = session.exec(select(Track)).all()
    assert len(tracks) == 1
    assert tracks[0].file_name == "test_track.mp3"


def test_scan_clears_hash_when_file_changes(
    tmp_path, test_collection, session, fixtures_dir
):
    scanned_file = tmp_path / "test_track.mp3"
    shutil.copy(fixtures_dir / "test_track.mp3", scanned_file)

    collection_id = test_collection
    scan_folder(str(tmp_path), collection_id=collection_id, session=session)
    track = session.exec(
        select(Track).where(
            Track.file_name == "test_track.mp3",
            Track.collection_id == collection_id,
        )
    ).one()
    track.file_hash = "dummyhash"
    session.add(track)
    session.commit()

    # Retag in place rather than swapping in a different file: file_path is
    # the row's identity, so a swap would have to keep the same path anyway,
    # and retagging keeps the format honest (the old version copied a FLAC
    # onto a .mp3 path, leaving format="MP3" describing FLAC audio).
    audio = mutagen.File(str(scanned_file), easy=True)
    audio["title"] = "Retagged Title"
    audio.save()

    result = scan_folder(str(tmp_path), collection_id=collection_id, session=session)

    assert result.updated == 1
    assert result.added == 0
    assert result.deleted == 0
    # one(), not first(): a re-scan that inserted instead of matching would
    # otherwise leave the original row around for these assertions to find.
    track = session.exec(select(Track)).one()
    assert track.title == "Retagged Title"
    assert track.file_hash is None


def test_scan_preserves_hash_when_file_unchanged(
    tmp_path, test_collection, session, fixtures_dir
):
    shutil.copy(fixtures_dir / "test_track.mp3", tmp_path / "test_track.mp3")

    collection_id = test_collection
    scan_folder(str(tmp_path), collection_id=collection_id, session=session)
    track = session.exec(
        select(Track).where(
            Track.file_name == "test_track.mp3",
            Track.collection_id == collection_id,
        )
    ).one()
    track.file_hash = "dummyhash"
    session.add(track)
    session.commit()

    # Nothing touches the file between the two scans: the walk still visits
    # it and compares every scanned field, so this is the path that must
    # leave the cached hash alone.
    result = scan_folder(str(tmp_path), collection_id=collection_id, session=session)

    assert result.updated == 0
    assert result.added == 0
    # one(), not first(): a re-scan that inserted a duplicate row instead of
    # matching the existing one would otherwise slip past the hash assertion.
    assert session.exec(select(Track)).one().file_hash == "dummyhash"


def test_scan_treats_case_only_rename_as_a_new_file(
    tmp_path, test_collection, session, fixtures_dir
):
    scanned_file = tmp_path / "test_track.mp3"
    shutil.copy(fixtures_dir / "test_track.mp3", scanned_file)

    collection_id = test_collection
    scan_folder(str(tmp_path), collection_id=collection_id, session=session)

    # The reconciliation index is keyed by exact path, so a case-only rename
    # is a different key: the old row goes stale and a new one is inserted.
    # Casefolding the key would make this an update instead, at the cost of
    # collapsing two genuinely distinct files into one row on a
    # case-sensitive filesystem. Pinning the delete-plus-insert here so the
    # keying can't quietly revert. See spec §12.
    renamed_file = tmp_path / "TEST_TRACK.MP3"
    os.replace(scanned_file, renamed_file)

    result = scan_folder(str(tmp_path), collection_id=collection_id, session=session)

    assert result.added == 1
    assert result.deleted == 1
    assert result.matched == 0
    track = session.exec(select(Track)).one()
    assert track.file_path == os.path.normpath(str(renamed_file))
    assert track.file_name == "TEST_TRACK.MP3"


def test_scan_clears_hash_when_only_file_size_changes(
    tmp_path, test_collection, session, fixtures_dir
):
    scanned_file = tmp_path / "test_track.mp3"
    shutil.copy(fixtures_dir / "test_track.mp3", scanned_file)

    collection_id = test_collection
    scan_folder(str(tmp_path), collection_id=collection_id, session=session)
    track = session.exec(
        select(Track).where(
            Track.file_name == "test_track.mp3",
            Track.collection_id == collection_id,
        )
    ).one()
    track.file_hash = "dummyhash"
    original_size = track.file_size
    session.add(track)
    session.commit()

    # composer is not a tag read_track reads, so writing a long one grows the
    # file past its ID3 padding while every scanned field except file_size
    # stays byte-identical. Same shape as a tagger embedding album art. This
    # is the case that slips through if file_size is left out of
    # SCANNED_FIELDS: a stale size in the matcher's size index, plus a cached
    # hash that no longer describes the bytes.
    audio = mutagen.File(str(scanned_file), easy=True)
    audio["composer"] = "x" * 20_000
    audio.save()

    result = scan_folder(str(tmp_path), collection_id=collection_id, session=session)

    assert result.updated == 1
    assert result.added == 0
    assert result.deleted == 0
    assert result.matched == 1
    track = session.exec(select(Track)).one()
    assert track.file_size == scanned_file.stat().st_size
    assert track.file_size != original_size
    assert track.file_hash is None


def test_scan_skips_superseded_directory(
    tmp_path, test_collection, session, fixtures_dir
):

    superseded_dir = tmp_path / SUPERSEDED_DIR_NAME
    superseded_dir.mkdir()
    (superseded_dir / "test_superseded.mp3").write_text("not audio")

    collection_id = test_collection
    result1 = scan_folder(str(tmp_path), collection_id=collection_id, session=session)

    assert result1.scanned == 0
    assert result1.added == 0
    assert result1.skipped_non_audio == 0

    shutil.copy(fixtures_dir / "test_track.mp3", superseded_dir / "test_superseded.mp3")
    shutil.copy(fixtures_dir / "test_track.mp3", tmp_path / "test_track.mp3")

    result2 = scan_folder(str(tmp_path), collection_id=collection_id, session=session)

    assert result2.scanned == 1
    assert result2.added == 1
    assert result2.skipped_non_audio == 0


def test_scan_sets_last_scanned_at(tmp_path, test_collection, session, fixtures_dir):
    shutil.copy(fixtures_dir / "test_track.mp3", tmp_path / "test_track.mp3")

    collection_id = test_collection
    result1 = scan_folder(str(tmp_path), collection_id=collection_id, session=session)

    assert result1.added == 1
    collection = session.get(Collection, collection_id)
    last_scanned_at1 = collection.last_scanned_at

    result2 = scan_folder(str(tmp_path), collection_id=collection_id, session=session)

    assert result2.added == 0
    collection = session.get(Collection, collection_id)
    last_scanned_at2 = collection.last_scanned_at

    assert last_scanned_at2 > last_scanned_at1


def test_scan_does_not_delete_rows_when_the_root_is_unreadable(
    tmp_path, test_collection, session, fixtures_dir
):
    shutil.copy(fixtures_dir / "test_track.mp3", tmp_path / "a.mp3")
    shutil.copy(fixtures_dir / "test_track.flac", tmp_path / "b.flac")

    collection_id = test_collection
    scan_folder(str(tmp_path), collection_id=collection_id, session=session)
    assert len(session.exec(select(Track)).all()) == 2

    # The drive goes away between scans. os.walk reports this through
    # onerror and then yields nothing at all, so every row looks stale.
    # Deleting on that evidence is how a disconnected drive wipes a catalog.
    shutil.rmtree(tmp_path)

    result = scan_folder(str(tmp_path), collection_id=collection_id, session=session)

    assert result.deleted == 0
    assert result.unreadable_directories == [os.path.normpath(str(tmp_path))]
    assert len(session.exec(select(Track)).all()) == 2


def test_scan_still_deletes_rows_outside_an_unreadable_subtree(
    tmp_path, test_collection, session, fixtures_dir, monkeypatch
):
    shutil.copy(fixtures_dir / "test_track.mp3", tmp_path / "a.mp3")
    shutil.copy(fixtures_dir / "test_track.flac", tmp_path / "b.flac")

    collection_id = test_collection
    scan_folder(str(tmp_path), collection_id=collection_id, session=session)

    (tmp_path / "b.flac").unlink()

    # A permission error somewhere unrelated must not veto every deletion:
    # every Windows drive root has an unreadable System Volume Information,
    # so a blanket veto would disable cleanup permanently on real drives.
    # Injected rather than provoked, because making a directory genuinely
    # unreadable needs different tooling on Windows and Linux.
    locked_dir = tmp_path / "locked"
    real_walk = os.walk

    def walk_with_error(top, **kwargs):
        onerror = kwargs.pop("onerror", None)
        yield from real_walk(top, **kwargs)
        if onerror is not None:
            onerror(PermissionError(13, "Access is denied", str(locked_dir)))

    monkeypatch.setattr(scanner.os, "walk", walk_with_error)

    result = scan_folder(str(tmp_path), collection_id=collection_id, session=session)

    assert result.deleted == 1
    assert result.unreadable_directories == [os.path.normpath(str(locked_dir))]
    assert session.exec(select(Track)).one().file_name == "a.mp3"


def test_scan_progress_runs_once_for_each_file(
    tmp_path, test_collection, session, fixtures_dir
):
    copies = {
        "a.mp3": "test_track.mp3",
        "b.flac": "test_track.flac",
        "c.mp3": "test_track.mp3",
    }
    for name, fixture in copies.items():
        shutil.copy(fixtures_dir / fixture, tmp_path / name)
    # Cover art is what gives this test the power to fail. The reported path
    # is computed once for every file, but only the audio branch used to
    # compute it, so a folder whose first entry is not audio raised
    # UnboundLocalError. Without a non-audio file here, that branch never runs.
    (tmp_path / "cover.jpg").write_text("not audio")

    files_on_disk = {
        os.path.normpath(str(tmp_path / name)) for name in (*copies, "cover.jpg")
    }

    collection_id = test_collection
    events = []
    result = scan_folder(
        str(tmp_path),
        collection_id=collection_id,
        session=session,
        on_progress=events.append,
    )

    paths = [e.current_path for e in events if e.current_path is not None]

    # scanned, not added: every file gets a report, audio or not. The two
    # agree only while every file is both audio and new, which is exactly the
    # fixture this test deliberately no longer has.
    assert len(paths) == result.scanned
    assert set(paths) == files_on_disk


def test_scan_progress_last_report_counts_equal_scan_result(
    tmp_path, test_collection, session, fixtures_dir
):
    shutil.copy(fixtures_dir / "test_track.mp3", tmp_path / "unchanged.mp3")
    shutil.copy(fixtures_dir / "test_track.mp3", tmp_path / "grown.mp3")
    shutil.copy(fixtures_dir / "test_track.mp3", tmp_path / "removed.mp3")

    collection_id = test_collection
    scan_folder(str(tmp_path), collection_id=collection_id, session=session)

    # The second scan is arranged so no counter lands on zero. An assertion
    # comparing 0 with 0 holds whatever the code does, and deleted was exactly
    # that: it is only ever non-zero because report() runs after the stale-row
    # loop, so a first-scan-only fixture cannot detect that call going missing.
    #
    # composer is not a tag read_track reads, so a long one grows the file
    # while every other scanned field stays identical. Same method, and same
    # reason, as test_scan_clears_hash_when_only_file_size_changes above.
    audio = mutagen.File(str(tmp_path / "grown.mp3"), easy=True)
    audio["composer"] = "x" * 20_000
    audio.save()
    os.remove(tmp_path / "removed.mp3")
    shutil.copy(fixtures_dir / "test_track.flac", tmp_path / "added.flac")
    (tmp_path / "cover.jpg").write_text("not audio")

    events = []
    result = scan_folder(
        str(tmp_path),
        collection_id=collection_id,
        session=session,
        on_progress=events.append,
    )

    assert (
        result.scanned,
        result.added,
        result.skipped_non_audio,
        result.updated,
        result.deleted,
        result.matched,
    ) == (4, 1, 1, 1, 1, 2)

    last_event = events[-1]

    assert last_event.scanned == result.scanned
    assert last_event.added == result.added
    assert last_event.skipped_non_audio == result.skipped_non_audio
    assert last_event.updated == result.updated
    assert last_event.deleted == result.deleted
    assert last_event.matched == result.matched


def test_scan_skips_apple_double_sidecars(
    tmp_path, test_collection, session, fixtures_dir
):
    # A real AppleDouble file: magic 0x00051607, then version and filler. macOS
    # leaves one beside every file it copies to exFAT, FAT32 or NTFS, so a
    # friend's Mac-written USB drive carries one per track — and each inherits
    # the real track's extension, which is what gets it past the allowlist.
    apple_double = bytes([0x00, 0x05, 0x16, 0x07, 0x00, 0x02, 0x00, 0x00]) + bytes(4000)
    shutil.copy(fixtures_dir / "test_track.mp3", tmp_path / "Creep.mp3")
    (tmp_path / "._Creep.mp3").write_bytes(apple_double)

    result = scan_folder(str(tmp_path), collection_id=test_collection, session=session)

    # Not on unreadable_files, which is the point. Before this guard, mutagen
    # raised HeaderNotFoundError on every sidecar and the scan reported a
    # warning naming thousands of files that were never broken.
    assert result.unreadable_files == []
    assert result.scanned == 2
    assert result.skipped_non_audio == 1
    # The real track beside it still lands. A guard that matched too greedily
    # would take Creep.mp3 along with ._Creep.mp3.
    assert result.added == 1
    assert session.exec(select(Track)).one().file_name == "Creep.mp3"


def test_a_changed_file_clears_the_fingerprint(
    tmp_path, test_collection, session, fixtures_dir
):
    scanned_file = tmp_path / "test_track.mp3"
    shutil.copy(fixtures_dir / "test_track.mp3", scanned_file)

    collection_id = test_collection
    scan_folder(str(tmp_path), collection_id=collection_id, session=session)
    track = session.exec(
        select(Track).where(
            Track.file_name == "test_track.mp3",
            Track.collection_id == collection_id,
        )
    ).one()
    track.fingerprint = pack_fingerprint([1, 2, 3])
    track.fingerprint_length = FPCALC_LENGTH_SECONDS
    track.fingerprint_algorithm = FPCALC_ALGORITHM
    session.add(track)
    session.commit()

    # Retag in place rather than swapping in a different file: file_path is
    # the row's identity, so a swap would have to keep the same path anyway,
    # and retagging keeps the format honest (the old version copied a FLAC
    # onto a .mp3 path, leaving format="MP3" describing FLAC audio).
    audio = mutagen.File(str(scanned_file), easy=True)
    audio["title"] = "Retagged Title"
    audio.save()

    result = scan_folder(str(tmp_path), collection_id=collection_id, session=session)

    assert result.updated == 1
    assert result.added == 0
    assert result.deleted == 0
    # one(), not first(): a re-scan that inserted instead of matching would
    # otherwise leave the original row around for these assertions to find.
    track = session.exec(select(Track)).one()
    assert track.title == "Retagged Title"
    assert track.fingerprint is None
    assert track.fingerprint_length is None
    assert track.fingerprint_algorithm is None
