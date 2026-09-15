# tests/test_scanner.py
import logging
import os
import shutil
import struct
import types

import mutagen
import pytest
from sqlmodel import select

import scanner
from fingerprinting import FPCALC_ALGORITHM, FPCALC_LENGTH_SECONDS, pack_fingerprint
from importing import SUPERSEDED_DIR_NAME
from matching import FORMAT_RANK
from models import Collection, Track
from scanner import (
    ALLOWED_EXTENSIONS,
    OGG_STREAM_FORMATS,
    WAVPACK_DSD_FLAG,
    WAVPACK_HYBRID_FLAG,
    WMA_CODEC_FORMATS,
    read_track,
    scan_folder,
    track_format,
    track_number_from_tag,
    wavpack_format,
    year_from_date,
)


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


def test_read_track_alac(test_collection, fixtures_dir):
    track = read_track(
        str(fixtures_dir / "test_track_alac.m4a"), collection_id=test_collection
    )

    assert track is not None
    assert track.file_name == "test_track_alac.m4a"
    assert track.title == "Test Track ALAC"
    assert track.artist == "Music Zamlr Fixtures"
    assert track.album == "Synthetic Test Album"
    assert track.track_number == 3
    assert track.year == 2026
    assert track.format == "ALAC"
    assert track.bit_depth == 24
    assert track.bit_rate == 2304000
    assert track.sample_rate == 48000
    assert track.duration == 1
    assert track.file_size == 115334
    assert track.file_hash is None
    assert track.collection_id == test_collection


def test_read_track_aac(test_collection, fixtures_dir):
    track = read_track(
        str(fixtures_dir / "test_track_aac.m4a"), collection_id=test_collection
    )

    assert track is not None
    assert track.file_name == "test_track_aac.m4a"
    assert track.title == "Test Track AAC"
    assert track.artist == "Music Zamlr Fixtures"
    assert track.album == "Synthetic Test Album"
    assert track.track_number == 3
    assert track.year == 2026
    assert track.format == "AAC"
    assert track.bit_rate == 217274
    assert track.sample_rate == 44100
    assert track.duration == 1
    assert track.file_size == 28926
    assert track.file_hash is None
    assert track.collection_id == test_collection


def test_read_track_aiff(test_collection, fixtures_dir):
    # The tags live in an ID3 chunk inside the AIFF file, which mutagen serves
    # only by frame id. Without that path, every tag below reads as None.
    track = read_track(
        str(fixtures_dir / "test_track.aiff"), collection_id=test_collection
    )

    assert track is not None
    assert track.title == "Test Track AIFF"
    assert track.artist == "Music Zamlr Fixtures"
    assert track.album == "Synthetic Test Album"
    assert track.track_number == 3
    assert track.year == 2026
    assert track.format == "AIFF"
    assert track.bit_depth == 16
    assert track.bit_rate == 705600
    assert track.sample_rate == 44100
    assert track.duration == 1
    assert track.file_size == 88430


def test_read_track_raw_aac_with_an_id3_tag(test_collection, fixtures_dir):
    # The fixture starts with an ID3 tag, which makes mutagen's detection pick
    # the MP3 reader. A None here means the AAC reader was not chosen.
    track = read_track(
        str(fixtures_dir / "test_track.aac"), collection_id=test_collection
    )

    assert track is not None
    assert track.title == "Test Track AAC"
    assert track.artist == "Music Zamlr Fixtures"
    assert track.album == "Synthetic Test Album"
    assert track.track_number == 3
    assert track.year == 2026
    assert track.format == "AAC"
    assert track.sample_rate == 44100
    assert track.duration == 1
    assert track.file_size == 16790
    # isinstance as well as ==, because mutagen gives this bitrate as the float
    # 125049.0, and 125049.0 == 125049 is true in Python.
    assert track.bit_rate == 125049
    assert isinstance(track.bit_rate, int)


def test_read_track_opus(test_collection, fixtures_dir):
    track = read_track(
        str(fixtures_dir / "test_track.opus"), collection_id=test_collection
    )

    assert track is not None
    assert track.title == "Test Track OPUS"
    assert track.artist == "Music Zamlr Fixtures"
    assert track.album == "Synthetic Test Album"
    assert track.track_number == 3
    assert track.year == 2026
    assert track.format == "OPUS"
    assert track.bit_rate == 112336
    # Opus reports no sample rate, and 0 is how the column records that.
    assert track.sample_rate == 0
    assert track.duration == 1
    assert track.file_size == 14282


def test_read_track_tta(test_collection, fixtures_dir):
    # The tags are APEv2, which the TrueAudio reader does not load, and the
    # file reports no bitrate and no bit depth.
    track = read_track(
        str(fixtures_dir / "test_track.tta"), collection_id=test_collection
    )

    assert track is not None
    assert track.title == "Test Track TTA"
    assert track.artist == "Music Zamlr Fixtures"
    assert track.album == "Synthetic Test Album"
    assert track.track_number == 3
    assert track.year == 2026
    assert track.format == "TTA"
    assert track.bit_rate == 0
    assert track.bit_depth is None
    assert track.sample_rate == 44100
    assert track.duration == 1
    assert track.file_size == 14788


# The files hold a stream header and APEv2 tags, and no audio. The tags need
# their own path: "track" and "year" are not easy-tag names, so without it
# the track number and the year read as None.
@pytest.mark.parametrize(
    "file_name, expected_format, title",
    [
        ("test_track.tak", "TAK", "Test Track TAK"),
        ("test_track.ofr", "OPTIMFROG", "Test Track OFR"),
    ],
    ids=["tak", "optimfrog"],
)
def test_read_track_header_only_files(
    make_header_only_file, test_collection, file_name, expected_format, title
):
    path = make_header_only_file(file_name)

    track = read_track(str(path), collection_id=test_collection)

    assert track is not None
    assert track.format == expected_format
    assert track.title == title
    assert track.artist == "Music Zamlr Fixtures"
    assert track.album == "Synthetic Test Album"
    assert track.track_number == 3
    assert track.year == 2026
    assert track.bit_depth == 24
    assert track.sample_rate == 96000
    assert track.duration == 3
    # Neither reader reports a bitrate.
    assert track.bit_rate == 0


# DSF and DFF files hold ID3 tags, which the ID3 path reads. The bitrate is
# the one that mutagen computes: 2,822,400 samples a second for each of 2
# channels, at 1 bit a sample.
@pytest.mark.parametrize(
    "file_name, title",
    [
        ("test_track.dsf", "Test Track DSF"),
        ("test_track.dff", "Test Track DFF"),
    ],
    ids=["dsf", "dff"],
)
def test_read_track_dsd_files(make_dsd_file, test_collection, file_name, title):
    path = make_dsd_file(file_name)

    track = read_track(str(path), collection_id=test_collection)

    assert track is not None
    assert track.format == "DSD"
    assert track.title == title
    assert track.artist == "Music Zamlr Fixtures"
    assert track.album == "Synthetic Test Album"
    assert track.track_number == 3
    assert track.year == 2026
    assert track.bit_depth == 1
    assert track.sample_rate == 2822400
    assert track.bit_rate == 5644800
    assert track.duration == 2


def test_read_track_ape(test_collection, fixtures_dir):
    # The tags are APEv2 under "Track" and "Year". Monkey's Audio reports no
    # bitrate, and 0 records that.
    track = read_track(
        str(fixtures_dir / "test_track.ape"), collection_id=test_collection
    )

    assert track is not None
    assert track.title == "Test Track APE"
    assert track.artist == "Music Zamlr Fixtures"
    assert track.album == "Synthetic Test Album"
    assert track.track_number == 3
    assert track.year == 2026
    assert track.format == "APE"
    assert track.bit_depth == 16
    assert track.bit_rate == 0
    assert track.sample_rate == 44100
    assert track.duration == 1
    assert track.file_size == 12752


def test_read_track_wavpack(fixtures_dir, test_collection):
    track = read_track(
        str(fixtures_dir / "test_track.wv"), collection_id=test_collection
    )

    assert track is not None
    assert track.title == "Test Track WAVPACK"
    assert track.artist == "Music Zamlr Fixtures"
    assert track.album == "Synthetic Test Album"
    assert track.track_number == 3
    assert track.year == 2026
    assert track.format == "WAVPACK"
    assert track.bit_depth == 16
    assert track.bit_rate == 0
    assert track.sample_rate == 44100
    assert track.duration == 1
    assert track.file_size == 35924


def test_read_track_names_a_hybrid_wavpack_file_lossy(
    fixtures_dir, tmp_path, test_collection
):
    # Only the hybrid bit changes, and mutagen ignores it, so the copy still
    # opens. The format then proves that track_format reads the flags from
    # the file itself.
    fixture = bytearray((fixtures_dir / "test_track.wv").read_bytes())
    flags = struct.unpack_from("<I", fixture, 24)[0]
    struct.pack_into("<I", fixture, 24, flags | WAVPACK_HYBRID_FLAG)

    hybrid_file = tmp_path / "test_track_hybrid.wv"
    hybrid_file.write_bytes(fixture)

    track = read_track(str(hybrid_file), collection_id=test_collection)

    assert track is not None
    assert track.format == "WAVPACK HYBRID"


def test_read_track_refuses_dsd_inside_wavpack(
    fixtures_dir, tmp_path, test_collection, caplog
):
    fixture = bytearray((fixtures_dir / "test_track.wv").read_bytes())
    flags = struct.unpack_from("<I", fixture, 24)[0]
    struct.pack_into("<I", fixture, 24, flags | WAVPACK_DSD_FLAG)

    dsd_file = tmp_path / "test_track_dsd.wv"
    dsd_file.write_bytes(fixture)

    # None alone passes whatever happens, because the broad catch in
    # read_track also returns None. The log levels show that the file was
    # refused on purpose: the broad catch writes at ERROR.
    caplog.set_level(logging.WARNING)
    track = read_track(str(dsd_file), collection_id=test_collection)

    assert track is None
    assert any(record.levelno == logging.WARNING for record in caplog.records)
    assert not any(record.levelno >= logging.ERROR for record in caplog.records)


def test_read_track_wma(test_collection, fixtures_dir):
    # The tags are ASF attributes under names of their own, such as "Author",
    # and WM/TrackNumber is a number, not text. WMA reports no bit depth.
    track = read_track(
        str(fixtures_dir / "test_track.wma"), collection_id=test_collection
    )

    assert track is not None
    assert track.title == "Test Track WMA"
    assert track.artist == "Music Zamlr Fixtures"
    assert track.album == "Synthetic Test Album"
    assert track.track_number == 3
    assert track.year == 2026
    assert track.format == "WMA"
    assert track.bit_depth is None
    assert track.bit_rate == 128000
    assert track.sample_rate == 44100
    assert track.duration == 1
    assert track.file_size == 21043


def test_read_track_names_wma_lossless_from_its_codec(
    fixtures_dir, tmp_path, test_collection
):
    # ffmpeg cannot encode WMA Lossless, so the copy changes only the codec id
    # in the codec list, which is where mutagen gets the codec name. In the
    # codec list, the id follows its length of 2. The id alone appears twice
    # in the file, so the count below keeps the patch on the right bytes.
    fixture = bytearray((fixtures_dir / "test_track.wma").read_bytes())
    codec_entry = struct.pack("<HH", 2, 0x0161)
    assert fixture.count(codec_entry) == 1
    struct.pack_into("<H", fixture, fixture.index(codec_entry) + 2, 0x0163)

    lossless_file = tmp_path / "test_track_lossless.wma"
    lossless_file.write_bytes(fixture)

    track = read_track(str(lossless_file), collection_id=test_collection)

    assert track is not None
    assert track.format == "WMA LOSSLESS"


def test_read_track_musepack(test_collection, fixtures_dir):
    # The tags are APEv2 under "Track" and "Year", as in the header-only files,
    # but this file holds real audio. Musepack reports no bit depth.
    track = read_track(
        str(fixtures_dir / "test_track.mpc"), collection_id=test_collection
    )

    assert track is not None
    assert track.title == "Test Track MUSEPACK"
    assert track.artist == "Music Zamlr Fixtures"
    assert track.album == "Synthetic Test Album"
    assert track.track_number == 3
    assert track.year == 2026
    assert track.format == "MUSEPACK"
    assert track.bit_depth is None
    assert track.bit_rate == 49520
    assert track.sample_rate == 44100
    assert track.duration == 1
    assert track.file_size == 6190


# One extension, three formats: the stream that mutagen detects decides. FLAC
# inside Ogg reports no bitrate and Opus no sample rate, and 0 records both.
@pytest.mark.parametrize(
    "file_name, expected_format, bit_depth, bit_rate, sample_rate, file_size",
    [
        ("test_track_vorbis.ogg", "VORBIS", None, 128000, 44100, 7189),
        ("test_track_opus.ogg", "OPUS", None, 112336, 0, 14282),
        ("test_track_flac.ogg", "FLAC", 16, 0, 44100, 12703),
    ],
    ids=["vorbis", "opus", "flac"],
)
def test_read_track_ogg_streams(
    test_collection,
    fixtures_dir,
    file_name,
    expected_format,
    bit_depth,
    bit_rate,
    sample_rate,
    file_size,
):
    track = read_track(str(fixtures_dir / file_name), collection_id=test_collection)

    assert track is not None
    assert track.format == expected_format
    assert track.title == f"Test Track {expected_format}"
    assert track.artist == "Music Zamlr Fixtures"
    assert track.album == "Synthetic Test Album"
    assert track.track_number == 3
    assert track.year == 2026
    assert track.bit_depth == bit_depth
    assert track.bit_rate == bit_rate
    assert track.sample_rate == sample_rate
    assert track.duration == 1
    assert track.file_size == file_size


@pytest.mark.parametrize(
    "file_path, codec, expected",
    [
        ("song.m4a", "alac", "ALAC"),
        ("song.m4a", "mp4a.40.2", "AAC"),
        ("song.m4a", "mp4a.40.5", "AAC"),
        ("song.m4a", "mp4a.40", "AAC"),
        ("SONG.M4A", "alac", "ALAC"),
        ("song.m4a", "mp4a.6B", None),
        ("song.m4a", "fLaC", None),
        ("song.m4a", None, None),
    ],
    ids=[
        "alac",
        "aac lc",
        "he-aac",
        "aac with no object type",
        "uppercase extension",
        "mp3 inside mp4",
        "flac inside mp4",
        "no codec",
    ],
)
def test_track_format_of_an_m4a_file_comes_from_its_codec(file_path, codec, expected):
    info = types.SimpleNamespace(codec=codec)

    assert track_format(file_path, info) == expected


def test_track_format_of_other_files_comes_from_the_extension():
    info = types.SimpleNamespace()

    assert track_format("song.flac", info) == "FLAC"


@pytest.mark.parametrize(
    "file_path, expected",
    [
        ("song.mp3", "MP3"),
        ("song.flac", "FLAC"),
        ("song.wav", "WAV"),
        ("song.aif", "AIFF"),
        ("song.aiff", "AIFF"),
        ("SONG.AIFF", "AIFF"),
        ("song.aac", "AAC"),
        ("song.opus", "OPUS"),
        ("song.tta", "TTA"),
        ("song.ape", "APE"),
        ("song.tak", "TAK"),
        ("song.ofr", "OPTIMFROG"),
        ("song.mpc", "MUSEPACK"),
        ("song.dsf", "DSD"),
        ("song.dff", "DSD"),
        ("song.xyz", None),
    ],
    ids=[
        "mp3",
        "flac",
        "wav",
        "aif",
        "aiff",
        "uppercase aiff",
        "aac",
        "opus",
        "tta",
        "ape",
        "tak",
        "optimfrog",
        "musepack",
        "dsf",
        "dff",
        "unknown extension",
    ],
)
def test_track_format_names_each_extension(file_path, expected):
    assert track_format(file_path, types.SimpleNamespace()) == expected


def test_every_allowed_extension_names_a_ranked_format():
    # A format that FORMAT_RANK does not know ranks worst, so a lossless file
    # of mine would lose to any MP3. The .m4a and .ogg formats come from the
    # content: .m4a has no table, so its two are named here, and .ogg's come
    # from its table, so a stream added to it cannot miss a rank.
    formats = (
        {
            track_format(f"song{extension}", types.SimpleNamespace())
            for extension in ALLOWED_EXTENSIONS - {".m4a", ".ogg", ".wv", ".wma"}
        }
        | {"ALAC", "AAC"}
        | {"WAVPACK", "WAVPACK HYBRID"}
        | set(WMA_CODEC_FORMATS.values())
        | set(OGG_STREAM_FORMATS.values())
    )

    assert None not in formats
    assert formats <= FORMAT_RANK.keys()


# The fixture's real flags set many other bits, so a mask that tests more than
# one bit fails that case. The DSD-and-hybrid case is the only one that fails
# when the hybrid bit is checked first.
@pytest.mark.parametrize(
    "flags, expected",
    [
        (0, "WAVPACK"),
        (WAVPACK_HYBRID_FLAG, "WAVPACK HYBRID"),
        (WAVPACK_DSD_FLAG, None),
        (WAVPACK_DSD_FLAG | WAVPACK_HYBRID_FLAG, None),
        (0x04BC1831, "WAVPACK"),
    ],
    ids=["no flags", "hybrid", "dsd", "dsd and hybrid", "fixture flags"],
)
def test_wavpack_format_reads_the_flags(flags, expected):
    header = struct.pack("<4s20xI4x", b"wvpk", flags)

    assert wavpack_format(header) == expected


@pytest.mark.parametrize(
    "header",
    [b"wvpk", b"RIFF" + bytes(28)],
    ids=["too short", "not wavpack"],
)
def test_wavpack_format_refuses_a_header_that_is_not_wavpack(header):
    assert wavpack_format(header) is None


@pytest.mark.parametrize(
    "codec_type, expected",
    [
        ("Windows Media Audio 9 Lossless", "WMA LOSSLESS"),
        ("Windows Media Audio Standard", "WMA"),
        ("Windows Media Audio 9 Standard", "WMA"),
        ("Windows Media Audio 9 Professional", "WMA"),
        ("Windows Media Audio 9 Voice", "WMA"),
        ("Windows Media Audio 10 Voice", "WMA"),
        ("Windows Media Audio Pro over SPDIF", None),
        ("", None),
    ],
    ids=[
        "lossless",
        "standard",
        "9 standard",
        "9 professional",
        "9 voice",
        "10 voice",
        "pro over spdif",
        "no codec list",
    ],
)
def test_track_format_of_a_wma_file_comes_from_its_codec_type(codec_type, expected):
    info = types.SimpleNamespace(codec_type=codec_type)

    assert track_format("song.wma", info) == expected


def test_every_wma_codec_name_is_a_name_that_mutagen_gives():
    # The keys are mutagen's names, not codec ids. A key that mutagen never
    # gives, from a typo or a renamed codec, would turn every file of that
    # codec into an unreadable file. The table is private to mutagen, so a
    # mutagen update that moves it fails here, which is the point.
    from mutagen.asf._util import CODECS

    assert WMA_CODEC_FORMATS.keys() <= set(CODECS.values())


def test_read_track_returns_none_for_an_unknown_m4a_codec(
    monkeypatch, fixtures_dir, test_collection
):
    monkeypatch.setattr("scanner.track_format", lambda path, info: None)

    track = read_track(
        str(fixtures_dir / "test_track_aac.m4a"), collection_id=test_collection
    )

    assert track is None


@pytest.mark.parametrize("extension", [".m4a", ".ogg", ".wv", ".wma"])
def test_read_track_warns_about_an_mp3_with_a_container_extension(
    tmp_path, fixtures_dir, test_collection, caplog, extension
):
    # mutagen detects the format from the content, so an MP3 file named .m4a
    # or .ogg arrives with MP3 stream information, which names neither
    # container's format. The result is None whether the file is turned away
    # with a warning or falls into the broad catch, so the log levels are the
    # assertion that matters: the broad catch writes at ERROR.
    misnamed = tmp_path / f"misnamed{extension}"
    shutil.copy(fixtures_dir / "test_track.mp3", misnamed)

    with caplog.at_level(logging.WARNING):
        track = read_track(str(misnamed), collection_id=test_collection)

    levels = [record.levelname for record in caplog.records]
    assert track is None
    assert "WARNING" in levels
    assert "ERROR" not in levels


def test_scan_folder_reads_m4a_files(fixtures_dir, tmp_path, test_collection, session):
    shutil.copy(fixtures_dir / "test_track_alac.m4a", tmp_path / "test_track_alac.m4a")
    shutil.copy(fixtures_dir / "test_track_aac.m4a", tmp_path / "test_track_aac.m4a")

    result = scan_folder(str(tmp_path), collection_id=test_collection, session=session)

    assert result.skipped_non_audio == 0
    assert result.added == 2

    tracks = session.exec(select(Track)).all()
    assert len(tracks) == 2
    formats = {t.format for t in tracks}
    assert formats == {"ALAC", "AAC"}


def test_scan_updates_the_format_when_the_codec_changes(
    fixtures_dir, tmp_path, test_collection, session
):
    shutil.copy(fixtures_dir / "test_track_alac.m4a", tmp_path / "song.m4a")

    scan_folder(str(tmp_path), collection_id=test_collection, session=session)

    shutil.copy(fixtures_dir / "test_track_aac.m4a", tmp_path / "song.m4a")

    scan_folder(str(tmp_path), collection_id=test_collection, session=session)

    tracks = session.exec(select(Track)).all()
    assert len(tracks) == 1
    assert tracks[0].format == "AAC"


def test_scan_folder_reads_aiff_aac_opus_and_tta_files(
    fixtures_dir, tmp_path, test_collection, session
):
    for name in (
        "test_track.aiff",
        "test_track.aac",
        "test_track.opus",
        "test_track.tta",
    ):
        shutil.copy(fixtures_dir / name, tmp_path / name)

    result = scan_folder(str(tmp_path), collection_id=test_collection, session=session)

    assert result.skipped_non_audio == 0
    assert result.unreadable_files == []
    tracks = session.exec(select(Track)).all()
    assert {t.format for t in tracks} == {"AIFF", "AAC", "OPUS", "TTA"}
    assert all(t.title is not None for t in tracks)


def test_scan_folder_reads_ogg_streams(
    fixtures_dir, tmp_path, test_collection, session
):
    # One name in capitals: the scanner accepts an extension in any case, and
    # track_format must still reach its .ogg branch for that file.
    shutil.copy(
        fixtures_dir / "test_track_vorbis.ogg", tmp_path / "TEST_TRACK_VORBIS.OGG"
    )
    shutil.copy(fixtures_dir / "test_track_opus.ogg", tmp_path / "test_track_opus.ogg")
    shutil.copy(fixtures_dir / "test_track_flac.ogg", tmp_path / "test_track_flac.ogg")

    result = scan_folder(str(tmp_path), collection_id=test_collection, session=session)

    assert result.skipped_non_audio == 0
    assert result.unreadable_files == []
    tracks = session.exec(select(Track)).all()
    assert {t.format for t in tracks} == {"VORBIS", "OPUS", "FLAC"}


def test_scan_folder_reads_apev2_tagged_formats(
    make_header_only_file, fixtures_dir, tmp_path, test_collection, session
):
    make_header_only_file("test_track.tak")
    make_header_only_file("test_track.ofr")
    shutil.copy(fixtures_dir / "test_track.mpc", tmp_path / "test_track.mpc")
    shutil.copy(fixtures_dir / "test_track.ape", tmp_path / "test_track.ape")
    shutil.copy(fixtures_dir / "test_track.wv", tmp_path / "test_track.wv")

    result = scan_folder(str(tmp_path), collection_id=test_collection, session=session)

    assert result.skipped_non_audio == 0
    assert result.unreadable_files == []
    tracks = session.exec(select(Track)).all()
    assert {t.format for t in tracks} == {
        "TAK",
        "OPTIMFROG",
        "MUSEPACK",
        "APE",
        "WAVPACK",
    }


def test_scan_folder_reads_wma_files(fixtures_dir, tmp_path, test_collection, session):
    shutil.copy(fixtures_dir / "test_track.wma", tmp_path / "test_track.wma")

    result = scan_folder(str(tmp_path), collection_id=test_collection, session=session)

    assert result.skipped_non_audio == 0
    assert result.unreadable_files == []
    assert session.exec(select(Track)).one().format == "WMA"


def test_scan_folder_reads_dsd_files(make_dsd_file, tmp_path, test_collection, session):
    make_dsd_file("test_track.dsf")
    make_dsd_file("test_track.dff")

    result = scan_folder(str(tmp_path), collection_id=test_collection, session=session)

    assert result.skipped_non_audio == 0
    assert result.unreadable_files == []
    tracks = session.exec(select(Track)).all()
    assert [t.format for t in tracks] == ["DSD", "DSD"]


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
