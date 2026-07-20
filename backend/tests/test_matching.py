
from pathlib import Path

from matching import match_collections

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_better_format_is_upgrade(make_track):
    mine = make_track(format="MP3", file_size=1_000_000)
    theirs = make_track(format="FLAC", file_size=2_000_000)
    result = match_collections([mine], [theirs])
    
    assert len(result.upgrade_available) == 1
    assert result.missing == []


def test_better_format_is_already_have(make_track):
    mine = make_track(format="FLAC", file_size=1_000_000)
    theirs = make_track(format="MP3", file_size=2_000_000)
    result = match_collections([mine], [theirs])

    assert len(result.already_have) == 1
    assert result.missing == []


def test_same_format_better_bitrate_is_upgrade(make_track):
    mine = make_track(format="MP3", bit_rate=320000, file_size=1_000_000)
    theirs = make_track(format="MP3", bit_rate=640000, file_size=2_000_000)
    result = match_collections([mine], [theirs])

    assert len(result.upgrade_available) == 1
    assert result.missing == []


def test_same_format_better_bitrate_is_already_have(make_track):
    mine = make_track(format="MP3", bit_rate=640000, file_size=1_000_000)
    theirs = make_track(format="MP3", bit_rate=320000, file_size=2_000_000)
    result = match_collections([mine], [theirs])

    assert len(result.already_have) == 1
    assert result.missing == []


def test_no_match_is_missing(make_track):
    mine = make_track(title="Some Title", artist="Some Artist", file_size=1_000_000)
    theirs = make_track(title="Some Other Title", artist="Some Other Artist", file_size=2_000_000)
    result = match_collections([mine], [theirs])

    assert len(result.missing) == 1
    assert result.upgrade_available == []
    assert result.already_have == []


def test_duration_at_tolerance_boundary_matches(make_track):
    mine = [make_track(duration=200, file_size=1_000_000)]
    theirs = [make_track(duration=202, file_size=2_000_000)]
    result = match_collections(mine, theirs)

    assert len(result.missing) == 0
    assert len(result.already_have) + len(result.upgrade_available) == 1


def test_duration_just_past_tolerance_is_missing(make_track):
    mine = [make_track(duration=200, file_size=1_000_000)]
    theirs = [make_track(duration=203, file_size=2_000_000)]
    result = match_collections(mine, theirs)

    assert len(result.missing) == 1
    assert len(result.only_in_mine) == 1


def test_ambiguous_match_is_needs_review(make_track):
    mine = [make_track(duration=120, file_size=1_000_000),
            make_track(duration=123, file_size=3_000_000)]
    theirs = [make_track(duration=121, file_size=2_000_000)]
    result = match_collections(mine, theirs)

    assert len(result.needs_review) == 1
    assert len(result.only_in_mine) == 2


def test_two_far_candidates_is_missing_not_review(make_track):
    mine = [make_track(duration=118, file_size=1_000_000),
            make_track(duration=124, file_size=3_000_000)]
    theirs = [make_track(duration=121, file_size=2_000_000)]
    result = match_collections(mine, theirs)

    assert len(result.missing) == 1
    assert result.needs_review == []
    assert len(result.only_in_mine) == 2


def test_empty_or_blank_title_is_missing(make_track):
    mine = [make_track(file_size=1_000_000),
            make_track(title="", artist="", file_size=2_000_000),
            make_track(title=None, artist=None, file_size=3_000_000)]
    theirs = [make_track(title="", file_size=4_000_000),
              make_track(title=None, file_size=5_000_000),
              make_track(artist="", file_size=6_000_000),
              make_track(artist=None, file_size=7_000_000),
              make_track(title="", artist="", file_size=8_000_000),
              make_track(title=None, artist=None, file_size=9_000_000)]
    result = match_collections(mine, theirs)
    
    assert len(result.missing) == 6
    assert result.upgrade_available == []
    assert result.already_have == []
    assert result.needs_review == []


def test_blank_tags_do_not_match_each_other(make_track):
    # Both sides blank on the same fields — the None == None trap.
    # Must NOT match; the blank-tag guard should send theirs to missing
    # and leave the blank mine-track untouched.
    blank_mine = make_track(title=None, artist=None, file_size=1_000_000)
    blank_theirs = make_track(title=None, artist=None, file_size=2_000_000)
    result = match_collections([blank_mine], [blank_theirs])

    assert len(result.missing) == 1
    assert result.missing[0] is blank_theirs
    assert result.already_have == []
    assert result.upgrade_available == []
    assert result.needs_review == []
    assert result.only_in_mine == [blank_mine]   # <- the mine-track was NOT consumed

def test_empty_tags_do_not_match_each_other(make_track):
    # Both sides blank on the same fields — the None == None trap.
    # Must NOT match; the blank-tag guard should send theirs to missing
    # and leave the blank mine-track untouched.
    empty_mine = make_track(title="", artist="", file_size=1_000_000)
    empty_theirs = make_track(title="", artist="", file_size=2_000_000)
    result = match_collections([empty_mine], [empty_theirs])

    assert len(result.missing) == 1
    assert result.missing[0] is empty_theirs
    assert result.already_have == []
    assert result.upgrade_available == []
    assert result.needs_review == []
    assert result.only_in_mine == [empty_mine]   # <- the mine-track was NOT consumed


def test_non_matching_mine_track_is_only_in_mine(make_track):
    mine = [make_track(title="Some Title", artist="Some Artist", file_size=1_000_000)]
    theirs = [make_track(title="Some Other Title", artist="Some Other Artist", file_size=2_000_000)]
    result = match_collections(mine, theirs)

    assert len(result.missing) == 1
    assert len(result.only_in_mine) == 1


def test_one_mine_is_matched_only_once(make_track):
    track_mine = make_track(file_size=1_000_000)
    mine = [track_mine]
    theirs = [make_track(file_size=2_000_000),
              make_track(file_size=3_000_000)]
    result = match_collections(mine, theirs)

    assert len(result.already_have) == 1
    assert result.already_have[0].mine is track_mine
    assert len(result.missing) == 1
    assert result.only_in_mine == []


def test_identical_files_match_by_hash(make_track):
    mine = [make_track(file_size=206_805, file_path=str(FIXTURES_DIR / "test_track_mine.mp3"), file_name="test_track.mp3")]
    theirs = [make_track(title=None, file_size=206_805, file_path=str(FIXTURES_DIR / "test_track_theirs.mp3"), file_name="test_track.mp3")]
    result = match_collections(mine, theirs)

    assert len(result.already_have) == 1


def test_same_size_different_content_no_hash_match(make_track):
    # Same size, different content → falls through to fuzzy tier (assert it doesn't false-match on hash).
    mine = [make_track(format="MP3", file_path=str(FIXTURES_DIR / "test_track.mp3"), file_name="test_track.mp3")]
    theirs = [make_track(format="FLAC", file_path=str(FIXTURES_DIR / "test_track.flac"), file_name="test_track.flac")]
    result = match_collections(mine, theirs)

    assert len(result.upgrade_available) == 1
    assert result.already_have == []
    assert result.upgrade_available[0].mine.file_hash != result.upgrade_available[0].theirs.file_hash