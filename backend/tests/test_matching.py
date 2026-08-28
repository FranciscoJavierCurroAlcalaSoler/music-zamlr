import pytest

from matching import match_collections


@pytest.fixture
def progress_tracks(make_track, fixtures_dir):
    """One track of mine and three of theirs, for the progress tests.

    The two lengths differ deliberately. With three a side, a matcher that
    reported len(tracks_mine) by mistake would satisfy every assertion about
    the total. Local to this module rather than in conftest.py, because only
    these tests want this shape.
    """

    def track(name, fmt):
        return make_track(
            format=fmt, file_path=str(fixtures_dir / name), file_name=name
        )

    mine = [track("test_track_mine.mp3", "MP3")]
    theirs = [
        track("test_track.flac", "FLAC"),
        track("test_track.mp3", "MP3"),
        track("test_track_theirs.mp3", "MP3"),
    ]
    return mine, theirs


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


def test_same_format_their_bitrate_none_is_already_have(make_track):
    mine = make_track(format="MP3", bit_rate=640000, file_size=1_000_000)
    theirs = make_track(format="MP3", bit_rate=None, file_size=2_000_000)
    result = match_collections([mine], [theirs])

    assert len(result.already_have) == 1


def test_same_format_my_bitrate_none_is_already_have(make_track):
    mine = make_track(format="MP3", bit_rate=None, file_size=1_000_000)
    theirs = make_track(format="MP3", bit_rate=320000, file_size=2_000_000)
    result = match_collections([mine], [theirs])

    assert len(result.already_have) == 1
    assert result.upgrade_available == []


def test_no_match_is_missing(make_track):
    mine = make_track(title="Some Title", artist="Some Artist", file_size=1_000_000)
    theirs = make_track(
        title="Some Other Title", artist="Some Other Artist", file_size=2_000_000
    )
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
    mine = [
        make_track(duration=120, file_size=1_000_000),
        make_track(duration=123, file_size=3_000_000),
    ]
    theirs = [make_track(duration=121, file_size=2_000_000)]
    result = match_collections(mine, theirs)

    (ambiguous,) = result.needs_review
    assert len(ambiguous.candidates) == 2
    # Neither candidate is worth acting on, so the UI has nothing to ask.
    assert {c.would_be for c in ambiguous.candidates} == {"already_have"}
    assert len(result.only_in_mine) == 2


def test_ambiguous_match_with_different_would_be(make_track):
    mine = [
        make_track(format="MP3", duration=120, file_size=1_000_000),
        make_track(format="FLAC", duration=123, file_size=3_000_000),
    ]
    theirs = [make_track(format="FLAC", duration=121, file_size=2_000_000)]
    result = match_collections(mine, theirs)

    (ambiguous,) = result.needs_review
    # Keyed by the attribute that decides the verdict rather than by
    # position: candidate order is currently the order of tracks_mine, but
    # the review dialog may well want them sorted, and that would break a
    # positional assertion without anything actually being wrong.
    would_be_by_format = {c.mine.format: c.would_be for c in ambiguous.candidates}
    assert would_be_by_format == {
        "FLAC": "already_have",
        "MP3": "upgrade_available",
    }
    assert len(result.only_in_mine) == 2


def test_two_far_candidates_is_missing_not_review(make_track):
    mine = [
        make_track(duration=118, file_size=1_000_000),
        make_track(duration=124, file_size=3_000_000),
    ]
    theirs = [make_track(duration=121, file_size=2_000_000)]
    result = match_collections(mine, theirs)

    assert len(result.missing) == 1
    assert result.needs_review == []
    assert len(result.only_in_mine) == 2


def test_their_duration_none_is_missing(make_track):
    mine = [
        make_track(duration=200, file_size=1_000_000),
    ]
    theirs = [
        make_track(duration=None, file_size=4_000_000),
    ]
    result = match_collections(mine, theirs)

    assert len(result.missing) == 1


def test_my_duration_none_with_matching_tags_is_missing(make_track):
    mine = [
        make_track(
            duration=None, title="A Title", artist="An Artist", file_size=1_000_000
        ),
    ]
    theirs = [
        make_track(
            duration=200, title="A Title", artist="An Artist", file_size=4_000_000
        ),
    ]
    result = match_collections(mine, theirs)

    assert len(result.missing) == 1
    assert result.missing[0] is theirs[0]
    assert len(result.only_in_mine) == 1
    assert result.only_in_mine[0] is mine[0]


def test_empty_or_blank_title_is_missing(make_track):
    mine = [
        make_track(file_size=1_000_000),
        make_track(title="", artist="", file_size=2_000_000),
        make_track(title=None, artist=None, file_size=3_000_000),
    ]
    theirs = [
        make_track(title="", file_size=4_000_000),
        make_track(title=None, file_size=5_000_000),
        make_track(artist="", file_size=6_000_000),
        make_track(artist=None, file_size=7_000_000),
        make_track(title="", artist="", file_size=8_000_000),
        make_track(title=None, artist=None, file_size=9_000_000),
    ]
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
    assert result.only_in_mine == [blank_mine]  # <- the mine-track was NOT consumed


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
    assert result.only_in_mine == [empty_mine]  # <- the mine-track was NOT consumed


def test_non_matching_mine_track_is_only_in_mine(make_track):
    mine = [make_track(title="Some Title", artist="Some Artist", file_size=1_000_000)]
    theirs = [
        make_track(
            title="Some Other Title", artist="Some Other Artist", file_size=2_000_000
        )
    ]
    result = match_collections(mine, theirs)

    assert len(result.missing) == 1
    assert len(result.only_in_mine) == 1


def test_one_mine_is_matched_only_once(make_track):
    track_mine = make_track(file_size=1_000_000)
    mine = [track_mine]
    theirs = [make_track(file_size=2_000_000), make_track(file_size=3_000_000)]
    result = match_collections(mine, theirs)

    assert len(result.already_have) == 1
    assert result.already_have[0].mine is track_mine
    assert len(result.missing) == 1
    assert result.only_in_mine == []


def test_identical_files_match_by_hash(make_track, fixtures_dir):
    mine = [
        make_track(
            file_size=206_805,
            file_path=str(fixtures_dir / "test_track_mine.mp3"),
            file_name="test_track.mp3",
        )
    ]
    theirs = [
        make_track(
            title=None,
            file_size=206_805,
            file_path=str(fixtures_dir / "test_track_theirs.mp3"),
            file_name="test_track.mp3",
        )
    ]
    result = match_collections(mine, theirs)

    assert len(result.already_have) == 1


def test_same_size_different_content_no_hash_match(make_track, fixtures_dir):
    # Same size, different content → falls through to fuzzy tier (assert it doesn't false-match on hash).
    mine = [
        make_track(
            format="MP3",
            file_path=str(fixtures_dir / "test_track.mp3"),
            file_name="test_track.mp3",
        )
    ]
    theirs = [
        make_track(
            format="FLAC",
            file_path=str(fixtures_dir / "test_track.flac"),
            file_name="test_track.flac",
        )
    ]
    result = match_collections(mine, theirs)

    assert len(result.upgrade_available) == 1
    assert result.already_have == []
    assert (
        result.upgrade_available[0].mine.file_hash
        != result.upgrade_available[0].theirs.file_hash
    )


def test_match_progress_names_each_track_before_counting_it(progress_tracks):
    mine, theirs = progress_tracks

    events = []
    match_collections(mine, theirs, on_progress=events.append)

    # The pairing is the claim, not the paths on their own. Reporting after
    # the work instead of before it yields the same paths in the same order
    # and only shifts each one against its count, so the count has to be in
    # the assertion for this test to notice. Built from theirs rather than
    # written out, so it cannot drift from the fixture.
    #
    # The last report names no file. It exists so a run ends on
    # processed == total instead of one short.
    assert [(e.theirs_processed_count, e.current_path) for e in events] == [
        *((index, track.file_path) for index, track in enumerate(theirs)),
        (len(theirs), None),
    ]


def test_match_progress_knows_the_total_from_the_first_report(progress_tracks):
    mine, theirs = progress_tracks

    events = []
    match_collections(mine, theirs, on_progress=events.append)

    # Fixed before any work happens. A determinate bar needs its maximum
    # before the first file is hashed, and a total the matcher accumulated as
    # it went would sit at 100% from the first frame to the last.
    assert events[0].theirs_count == len(theirs)
    assert events[0].theirs_processed_count == 0
    assert {event.theirs_count for event in events} == {len(theirs)}


def test_match_progress_counts_only_the_files_it_hashed(make_track, fixtures_dir):
    # The sizes are arbitrary labels and only equality between them matters:
    # a shared size is what puts two tracks in the same bucket of the size
    # index, which is the only thing that sends the matcher to the disk.
    mine = [
        make_track(
            format="MP3",
            file_size=206_805,
            file_path=str(fixtures_dir / "test_track_mine.mp3"),
            file_name="test_track_mine.mp3",
        ),
        make_track(
            format="FLAC",
            file_size=111_111,
            file_path=str(fixtures_dir / "test_track.flac"),
            file_name="test_track_mine.flac",
        ),
    ]
    theirs = [
        make_track(
            format="FLAC",
            file_size=206_805,
            file_path=str(fixtures_dir / "test_track.flac"),
            file_name="test_track.flac",
        ),
        make_track(
            format="MP3",
            file_size=999_999,
            file_path=str(fixtures_dir / "test_track.mp3"),
            file_name="test_track.mp3",
        ),
        make_track(
            format="MP3",
            file_size=206_805,
            file_path=str(fixtures_dir / "test_track_theirs.mp3"),
            file_name="test_track_theirs.mp3",
        ),
    ]

    events = []
    match_collections(mine, theirs, on_progress=events.append)

    # Three, and the fourth read is what this test forbids. theirs[0] shares a
    # size with mine[0], so both are opened. theirs[1] shares a size with
    # nothing and is never touched. theirs[2] shares that same size again and
    # is opened, but mine[0] already carries a hash from the first pairing and
    # must not be read a second time. Counting candidates examined rather than
    # files opened gives 4 here, and on a real re-run makes the number climb
    # while the diff reads no bytes at all.
    assert events[-1].hashed_count == 3


def test_lossless_wav_of_mine_is_not_upgraded_by_a_lossy_mp3(make_track):
    # WAV is uncompressed PCM, so it belongs with the other lossless formats.
    # Left out of FORMAT_RANK it scored 0 — below MP3 — and a 128 kbps file
    # counted as an upgrade over it. With the delete upgrade action that
    # destroys the WAV, which is why this pairing has a test of its own.
    mine = make_track(format="WAV", bit_rate=1_411_200, file_size=1_000_000)
    theirs = make_track(format="MP3", bit_rate=128_000, file_size=2_000_000)

    result = match_collections([mine], [theirs])

    assert result.upgrade_available == []
    assert len(result.already_have) == 1


def test_lossless_wav_of_theirs_upgrades_a_lossy_mp3_of_mine(make_track):
    # The other direction, which the missing rank got wrong too: theirs scored
    # 0 against my MP3's 1, so a real upgrade was hidden as already_have.
    mine = make_track(format="MP3", bit_rate=320_000, file_size=1_000_000)
    theirs = make_track(format="WAV", bit_rate=1_411_200, file_size=2_000_000)

    result = match_collections([mine], [theirs])

    assert len(result.upgrade_available) == 1
    assert result.already_have == []
