# tests/test_scanner.py
from pathlib import Path

from scanner import read_track, year_from_date, track_number_from_tag

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_read_track_mp3():
    track = read_track(str(FIXTURES_DIR / "test_track.mp3"))

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
    assert len(track.file_hash) == 64


def test_read_track_flac():
    track = read_track(str(FIXTURES_DIR / "test_track.flac"))

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
    assert len(track.file_hash) == 64


def test_read_track_nonexistent_file_returns_none():
    track = read_track(str(FIXTURES_DIR / "does_not_exist.mp3"))
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