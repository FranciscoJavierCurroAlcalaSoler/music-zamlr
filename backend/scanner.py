import logging
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

import mutagen
import mutagen.aac
from mutagen import MutagenError
from mutagen.apev2 import APEv2
from mutagen.id3 import ID3
from mutagen.oggflac import OggFLACStreamInfo
from mutagen.oggopus import OggOpusInfo
from mutagen.oggvorbis import OggVorbisInfo
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


# The ID3 frames that hold the values read_track asks for.
ID3_FRAMES = {
    "title": "TIT2",
    "artist": "TPE1",
    "album": "TALB",
    "date": "TDRC",
    "tracknumber": "TRCK",
}

# The APEv2 keys for the same values. mutagen compares APEv2 keys without
# case, and writers use "date" or "year" for the year, so both are read.
APE_KEYS = {
    "title": "title",
    "artist": "artist",
    "album": "album",
    "date": "date",
    "year": "year",
    "tracknumber": "track",
}


def _values_from_id3(tags) -> dict[str, list[str]]:
    values = {}
    for name, frame_id in ID3_FRAMES.items():
        frame = tags.get(frame_id)
        if frame is not None and frame.text:
            values[name] = [str(frame.text[0])]
    return values


def _values_from_ape(tags) -> dict[str, list[str]]:
    values = {}
    for name, key in APE_KEYS.items():
        value = tags.get(key)
        if value is not None:
            values[name] = [str(value)]
    return values


def tag_source(audio, file_path: str):
    """Return the object that get_tag reads: easy tags, or the same names.

    With easy=True, mutagen serves names such as "title" for most formats.
    Four kinds of file need more. AIFF and WAV keep ID3 inside their own
    chunks, and mutagen serves that ID3 only by frame id. Monkey's Audio, TAK,
    OptimFROG and Musepack files load APEv2 tags, which use "track" and "year"
    where easy tags use "tracknumber" and "date". A raw AAC file can start
    with an ID3 tag, which the AAC reader does not load. A TrueAudio file with
    APEv2 tags looks untagged, because its reader loads only ID3.

    A file with no readable tags gives an empty dict, so every tag reads as
    None. A damaged tag block gives the same result, because the audio is
    still readable and the file must still get a row.
    """
    if isinstance(audio.tags, ID3):
        return _values_from_id3(audio.tags)
    if isinstance(audio.tags, APEv2):
        return _values_from_ape(audio.tags)
    if audio.tags is not None:
        return audio
    try:
        return _values_from_id3(ID3(file_path))
    except MutagenError:
        pass
    try:
        return _values_from_ape(APEv2(file_path))
    except MutagenError:
        return {}


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


# The format for each extension that names exactly one format. .m4a is not
# here, because its codec names the format, in track_format.
EXTENSION_FORMATS = {
    ".mp3": "MP3",
    ".flac": "FLAC",
    ".wav": "WAV",
    ".aif": "AIFF",
    ".aiff": "AIFF",
    ".aac": "AAC",
    ".opus": "OPUS",
    ".tta": "TTA",
    ".ape": "APE",
    ".tak": "TAK",
    ".ofr": "OPTIMFROG",
    ".mpc": "MUSEPACK",
}

# The format for each stream that an .ogg file can hold, keyed by the stream
# information class that mutagen chose by reading the content. An MP3 file
# named .ogg arrives with MP3 stream information, which is not a key, so it
# gets no format.
OGG_STREAM_FORMATS = {
    OggVorbisInfo: "VORBIS",
    OggOpusInfo: "OPUS",
    OggFLACStreamInfo: "FLAC",
}


def track_format(file_path: str, info: object) -> str | None:
    """Name the format of a scanned file, or return None if it has none.

    Every format except .m4a and .ogg comes from EXTENSION_FORMATS, and an
    extension that the table does not know gets None. An .ogg file gets its
    format from OGG_STREAM_FORMATS. An .m4a file can hold
    ALAC, which is lossless, or AAC, which is lossy, so its codec decides.
    mutagen writes AAC as "mp4a.40" and an audio object type, and it writes no
    type when the stream has no decoder details. A bare "mp4a" prefix is not
    enough, because MP3 inside an MP4 reports "mp4a.6B".

    Any other codec gets None, never a new format name. A format that
    FORMAT_RANK does not know ranks worst, so a lossless file of mine would
    lose to any MP3, and the delete action would remove it.

    The codec is read only for .m4a, because mutagen gives the other formats
    no codec attribute. Even then it is read with getattr: mutagen detects the
    format from the content, not the name, so an MP3 file named .m4a arrives
    with no codec attribute at all.
    """
    extension = os.path.splitext(file_path)[1].lower()
    if extension == ".ogg":
        return OGG_STREAM_FORMATS.get(type(info))
    if extension != ".m4a":
        return EXTENSION_FORMATS.get(extension)
    codec = getattr(info, "codec", None)
    if codec is None:
        return None
    if codec == "alac":
        return "ALAC"
    if codec == "mp4a.40" or codec.startswith("mp4a.40."):
        return "AAC"
    return None


def open_audio(file_path: str):
    """Open a file with mutagen, and choose the reader where detection fails.

    A raw AAC file opens with the AAC reader directly. mutagen chooses a
    reader by score, and an ID3 tag at the start of a file scores 2 for MP3
    against 1 for the .aac extension. Detection then gives a tagged AAC file
    to the MP3 reader, which fails on it.
    """
    if os.path.splitext(file_path)[1].lower() == ".aac":
        return mutagen.aac.AAC(file_path)
    return mutagen.File(file_path, easy=True)


def read_track(file_path: str, collection_id: int) -> Track | None:
    try:
        audio = open_audio(file_path)
        fmt = track_format(file_path, audio.info)
        # Return before a Track exists. A row with no format ranks worst, and
        # this way the file appears in unreadable_files for the user to see.
        if fmt is None:
            logging.warning(
                "Could not determine format for file %s with codec %s.",
                file_path,
                getattr(audio.info, "codec", None),
            )
            return None

        tags = tag_source(audio, file_path)
        return Track(
            file_path=os.path.normpath(file_path),
            file_name=os.path.basename(file_path),
            # getattr with 0, because Opus reports no sample rate and
            # TrueAudio no bitrate. Neither column can hold None, and 0 counts
            # as unmeasured wherever they are compared. round, because a raw
            # AAC bitrate arrives as a float.
            bit_rate=round(getattr(audio.info, "bitrate", 0) or 0),
            sample_rate=getattr(audio.info, "sample_rate", 0) or 0,
            duration=round(audio.info.length),
            title=get_tag(tags, ["title"]),
            artist=get_tag(tags, ["artist"]),
            album=get_tag(tags, ["album"]),
            track_number=track_number_from_tag(get_tag(tags, ["tracknumber"])),
            year=year_from_date(get_tag(tags, ["date", "year"])),
            format=fmt,
            bit_depth=audio.info.bits_per_sample
            if hasattr(audio.info, "bits_per_sample")
            else None,
            file_size=os.path.getsize(file_path),
            collection_id=collection_id,
        )
    # Exception, not MutagenError, and wider than the project's rule on
    # purpose. scan_folder commits once at the end, so one exception that
    # leaves this function loses every row the scan has read. mutagen names
    # MutagenError as the base of its own exceptions, not as the only thing its
    # parsers can raise on a malformed file. The cost is that a bug here does
    # not raise. It is not silent either: every file becomes unreadable, and
    # logging.exception writes the traceback for each one.
    except Exception:
        logging.exception(f"Failed to read track information from {file_path}")
        return None


# Built from EXTENSION_FORMATS, so an allowed extension always has a format.
# .m4a and .ogg are added by hand, because their content names the format.
ALLOWED_EXTENSIONS = {*EXTENSION_FORMATS, ".m4a", ".ogg"}

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
# The fields that a re-scan compares with the stored row. format is one of
# them because an .m4a file gets its format from the codec, so the format can
# change while the path stays the same: an ALAC file re-encoded to AAC under
# its old name.
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
    "format",
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
                            existing_by_path[file_key].fingerprint_length = None
                            existing_by_path[file_key].fingerprint_algorithm = None
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
