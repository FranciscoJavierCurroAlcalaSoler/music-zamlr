import logging
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

import mutagen
from sqlmodel import Session, select

from database import create_collection, create_db_and_tables, engine
from importing import SUPERSEDED_DIR_NAME
from models import Collection, Track

logging.basicConfig(level=logging.INFO)


def get_tag(audio, keys: list[str]) -> str | None:
    for key in keys:
        value = audio.get(key, [None])[0]
        if value is not None and value != "":
            return value
    return None


def year_from_date(date_str: str | None) -> int | None:
    try:
        # Assuming the date is in the format 'YYYY-MM-DD' or 'YYYY'
        return int(date_str.split("-")[0])
    except (ValueError, AttributeError):
        return None


def track_number_from_tag(track_number_str: str | None) -> int | None:
    try:
        # Assuming the track number is in the format 'X/Y' or 'X'
        return int(track_number_str.split("/")[0])
    except (ValueError, AttributeError):
        return None


def read_track(file_path: str, collection_id: int) -> Track | None:
    try:
        audio = mutagen.File(file_path, easy=True)
        return Track(
            file_path=os.path.normpath(file_path),
            file_name=os.path.basename(file_path),
            bit_rate=audio.info.bitrate,
            sample_rate=audio.info.sample_rate,
            duration=round(audio.info.length),
            title=get_tag(audio, ["title"]),
            artist=get_tag(audio, ["artist"]),
            album=get_tag(audio, ["album"]),
            track_number=track_number_from_tag(get_tag(audio, ["tracknumber"])),
            year=year_from_date(get_tag(audio, ["date", "year"])),
            format=os.path.splitext(file_path)[1].upper().strip("."),
            bit_depth=audio.info.bits_per_sample
            if hasattr(audio.info, "bits_per_sample")
            else None,
            file_size=os.path.getsize(file_path),
            collection_id=collection_id,
        )
    except Exception as e:
        logging.error(f"Failed to read track information from {file_path}: {e}")
        return None


ALLOWED_EXTENSIONS = {
    ".mp3",
    ".flac",
    ".wav",
}  # placeholder, config file comes later

# macOS writes one of these beside every file it copies to a filesystem with
# no resource-fork support — which is every filesystem a drive needs to be
# readable on Windows: exFAT, FAT32, NTFS. So a friend's Mac-written USB drive
# carries one per track, and each one inherits the real track's extension:
# Creep.mp3 gets a ._Creep.mp3 next to it.
#
# They pass the extension allowlist, mutagen then raises HeaderNotFoundError,
# and without this they land on unreadable_files by the thousand — reported to
# the user as a warning that their drive could not be read.
APPLE_DOUBLE_PREFIX = "._"
BATCH_SIZE = 100  # placeholder, config file comes later
SCANNED_FIELDS = (
    "file_size",
    "bit_rate",
    "sample_rate",
    "duration",
    "title",
    "artist",
    "album",
    "track_number",
    "year",
    "bit_depth",
)


@dataclass
class ScanProgress:
    scanned: int
    added: int
    skipped_non_audio: int
    updated: int
    deleted: int
    matched: int
    current_path: str | None


@dataclass
class ScanResult:
    scanned: int
    added: int
    skipped_non_audio: int
    updated: int
    deleted: int
    matched: int
    collection: Collection
    # Two different failures, named on the same axis so the only difference
    # is the subject: a file we could not turn into a row, versus a
    # directory we could not open at all. The second one is why rows under
    # it were left alone instead of deleted.
    unreadable_files: list[str] = field(default_factory=list)
    unreadable_directories: list[str] = field(default_factory=list)


def scan_folder(
    folder_path: str,
    collection_id: int,
    session,
    # The on_progress default value None keeps existing call sites (tests,
    # endpoints, CLI) working.
    on_progress: Callable[[ScanProgress], None] | None = None,
) -> ScanResult:
    scanned_count = 0
    matched_count = 0
    updated_count = 0
    added_count = 0
    skipped_non_audio_count = 0
    deleted_count = 0
    pending_inserts = 0

    def report(current_path: str | None = None) -> None:
        if on_progress is not None:
            scan_progress = ScanProgress(
                scanned=scanned_count,
                added=added_count,
                updated=updated_count,
                matched=matched_count,
                deleted=deleted_count,
                skipped_non_audio=skipped_non_audio_count,
                current_path=current_path,
            )
            on_progress(scan_progress)

    collection = session.get(Collection, collection_id)
    if collection is None:
        raise ValueError(f"Collection with ID {collection_id} not found.")
    tracks = session.exec(
        select(Track).where(Track.collection_id == collection_id)
    ).all()
    # Keyed by exact path, deliberately not casefolded. Both halves of the
    # key are stable across scans: the caller passes the collection's stored
    # root_path verbatim, and os.walk reports on-disk casing for everything
    # below it. Casefolding here would fold Song.mp3 and song.mp3 into one
    # key on a case-sensitive filesystem, leaving the loser unreachable and
    # so never updated and never deleted. The trade is that a case-only
    # rename on Windows reads as a delete plus an insert, which costs that
    # file's cached hash and nothing else. See spec §12.
    existing_by_path = {os.path.normpath(track.file_path): track for track in tracks}
    expected_keys = set(existing_by_path.keys())
    visited_keys = set()
    superseded_folded = SUPERSEDED_DIR_NAME.casefold()

    unreadable_files: list[str] = []
    unreadable_directories: list[str] = []

    def record_unreadable_directory(error: OSError) -> None:
        logging.warning(f"Could not read {error.filename}: {error}")
        if error.filename:
            unreadable_directories.append(os.path.normpath(error.filename))

    report()
    for root, dirs, files in os.walk(folder_path, onerror=record_unreadable_directory):
        # Skip the superseded directory at any depth.
        dirs[:] = [d for d in dirs if d.casefold() != superseded_folded]
        for file in files:
            scanned_count += 1
            file_key = os.path.normpath(os.path.join(root, file))
            # Both conditions in one place, so there is exactly one branch that
            # counts a file as not-audio. That counter now means "seen and not
            # a track" rather than only "wrong extension".
            is_audio = file.lower().endswith(
                tuple(ALLOWED_EXTENSIONS)
            ) and not file.startswith(APPLE_DOUBLE_PREFIX)
            if is_audio:
                visited_keys.add(file_key)
                if file_key in expected_keys:
                    matched_count += 1
                    field_changed = False
                    updated_track = read_track(file_key, collection_id=collection_id)
                    if updated_track:
                        for field in SCANNED_FIELDS:
                            if getattr(existing_by_path[file_key], field) != getattr(
                                updated_track, field
                            ):
                                setattr(
                                    existing_by_path[file_key],
                                    field,
                                    getattr(updated_track, field),
                                )
                                field_changed = True
                        if field_changed:
                            updated_count += 1
                            existing_by_path[file_key].file_hash = None
                            existing_by_path[file_key].fingerprint = None
                    else:
                        unreadable_files.append(file_key)
                else:
                    new_track = read_track(file_key, collection_id=collection_id)
                    if new_track:
                        session.add(new_track)
                        added_count += 1
                        pending_inserts += 1
                    else:
                        unreadable_files.append(file_key)
                if pending_inserts >= BATCH_SIZE:
                    session.flush()
                    pending_inserts = 0
            else:
                skipped_non_audio_count += 1
            report(file_key)

    def under_unreadable_directory(path: str) -> bool:
        for bad_path in unreadable_directories:
            try:
                if os.path.commonpath([path, bad_path]) == bad_path:
                    return True
            except ValueError:
                continue  # different drives: not comparable, so not under it
        return False

    report()
    stale_keys = expected_keys - visited_keys
    for stale_key in stale_keys:
        if under_unreadable_directory(stale_key):
            continue
        stale_track = existing_by_path[stale_key]
        session.delete(stale_track)
        deleted_count += 1
    report()

    collection.last_scanned_at = datetime.now().isoformat()
    # This commit also flushes any pending inserts, so we don't need to flush before it.
    session.commit()

    return ScanResult(
        scanned=scanned_count,
        added=added_count,
        skipped_non_audio=skipped_non_audio_count,
        updated=updated_count,
        deleted=deleted_count,
        matched=matched_count,
        unreadable_files=unreadable_files,
        unreadable_directories=unreadable_directories,
        collection=collection,
    )


def main():
    if len(sys.argv) < 3:
        print("Usage: python scanner.py <folder_to_scan> <collection_name>")
        sys.exit(1)

    folder_to_scan = sys.argv[1]
    collection_name = sys.argv[2]
    create_db_and_tables()

    with Session(engine) as session:
        collection = create_collection(
            Collection(
                name=collection_name,
                root_path=os.path.normpath(folder_to_scan),
                last_scanned_at=None,
            ),
            session,
        )
        result = scan_folder(folder_to_scan, collection.id, session)

    print(result)


if __name__ == "__main__":
    main()
