import pytest

from enums import Bucket
from fingerprinting import FPCALC_ALGORITHM, FPCALC_LENGTH_SECONDS, pack_fingerprint
from matching import DURATION_TOLERANCE_SECONDS, classify_pairing, match_collections


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


def test_a_fingerprint_match_finds_an_upgrade_with_no_tags(
    make_track, fake_fingerprint
):
    fingerprint = pack_fingerprint(fake_fingerprint(1, 200))
    mine = [
        make_track(
            format="MP3",
            duration=200,
            file_size=1_000_000,
            title=None,
            artist=None,
            fingerprint=fingerprint,
            fingerprint_length=FPCALC_LENGTH_SECONDS,
            fingerprint_algorithm=FPCALC_ALGORITHM,
        ),
    ]
    theirs = [
        make_track(
            format="FLAC",
            duration=200,
            file_size=4_000_000,
            title=None,
            artist=None,
            fingerprint=fingerprint,
            fingerprint_length=FPCALC_LENGTH_SECONDS,
            fingerprint_algorithm=FPCALC_ALGORITHM,
        ),
    ]
    result = match_collections(mine, theirs)

    assert len(result.upgrade_available) == 1
    assert result.missing == []


def test_a_fingerprint_match_beats_a_wrong_tag(make_track, fake_fingerprint):
    fingerprint = pack_fingerprint(fake_fingerprint(2, 200))
    mine = [
        make_track(
            format="MP3",
            duration=200,
            file_size=1_000_000,
            title="A Title",
            artist="An Artist",
            fingerprint=fingerprint,
            fingerprint_length=FPCALC_LENGTH_SECONDS,
            fingerprint_algorithm=FPCALC_ALGORITHM,
        ),
    ]
    theirs = [
        make_track(
            format="FLAC",
            duration=200,
            file_size=4_000_000,
            title="Some Other Title",
            artist="Some Other Artist",
            fingerprint=fingerprint,
            fingerprint_length=FPCALC_LENGTH_SECONDS,
            fingerprint_algorithm=FPCALC_ALGORITHM,
        ),
    ]
    result = match_collections(mine, theirs)

    assert len(result.upgrade_available) == 1
    assert result.missing == []


def test_a_different_recording_of_the_same_length_is_not_matched(
    make_track, fake_fingerprint
):
    fingerprint1 = pack_fingerprint(fake_fingerprint(3, 200))
    fingerprint2 = pack_fingerprint(fake_fingerprint(4, 200))
    mine = [
        make_track(
            format="MP3",
            duration=201,
            file_size=1_000_000,
            title="A Title",
            artist="An Artist",
            fingerprint=fingerprint1,
            fingerprint_length=FPCALC_LENGTH_SECONDS,
            fingerprint_algorithm=FPCALC_ALGORITHM,
        ),
    ]
    theirs = [
        make_track(
            format="FLAC",
            duration=200,
            file_size=4_000_000,
            title="Some Other Title",
            artist="Some Other Artist",
            fingerprint=fingerprint2,
            fingerprint_length=FPCALC_LENGTH_SECONDS,
            fingerprint_algorithm=FPCALC_ALGORITHM,
        ),
    ]
    result = match_collections(mine, theirs)

    assert result.upgrade_available == []
    assert len(result.missing) == 1


def test_a_fingerprint_match_at_the_duration_boundary(make_track, fake_fingerprint):
    # Exactly DURATION_TOLERANCE_SECONDS apart, which is inside the window
    # because the tolerance is inclusive on both sides.
    #
    # This is the only fingerprint test whose durations differ at all on a
    # pair that matches. Every other one uses equal durations, so narrowing
    # the five buckets to the exact second leaves them all green — the
    # window would be dead code that no test defends.
    fingerprint = pack_fingerprint(fake_fingerprint(9, 200))
    mine = [
        make_track(
            format="MP3",
            duration=200,
            file_size=1_000_000,
            title=None,
            artist=None,
            fingerprint=fingerprint,
            fingerprint_length=FPCALC_LENGTH_SECONDS,
            fingerprint_algorithm=FPCALC_ALGORITHM,
        ),
    ]
    theirs = [
        make_track(
            format="FLAC",
            duration=200 + DURATION_TOLERANCE_SECONDS,
            file_size=4_000_000,
            title=None,
            artist=None,
            fingerprint=fingerprint,
            fingerprint_length=FPCALC_LENGTH_SECONDS,
            fingerprint_algorithm=FPCALC_ALGORITHM,
        ),
    ]
    result = match_collections(mine, theirs)

    assert len(result.upgrade_available) == 1
    assert result.missing == []


def test_a_duration_outside_the_tolerance_is_not_a_candidate(
    make_track, fake_fingerprint
):
    duration1 = 200
    duration2 = duration1 + DURATION_TOLERANCE_SECONDS + 1
    fingerprint = pack_fingerprint(fake_fingerprint(5, 200))
    mine = [
        make_track(
            duration=duration1,
            file_size=1_000_000,
            fingerprint=fingerprint,
            fingerprint_length=FPCALC_LENGTH_SECONDS,
            fingerprint_algorithm=FPCALC_ALGORITHM,
        ),
    ]
    theirs = [
        make_track(
            duration=duration2,
            file_size=4_000_000,
            fingerprint=fingerprint,
            fingerprint_length=FPCALC_LENGTH_SECONDS,
            fingerprint_algorithm=FPCALC_ALGORITHM,
        ),
    ]
    result = match_collections(mine, theirs)

    assert result.upgrade_available == []
    assert len(result.missing) == 1


def test_two_fingerprint_candidates_go_to_review(make_track, fake_fingerprint):
    fingerprint = pack_fingerprint(fake_fingerprint(6, 200))
    mine = [
        make_track(
            duration=200,
            file_size=1_000_000,
            fingerprint=fingerprint,
            fingerprint_length=FPCALC_LENGTH_SECONDS,
            fingerprint_algorithm=FPCALC_ALGORITHM,
        ),
        make_track(
            duration=200,
            file_size=3_000_000,
            fingerprint=fingerprint,
            fingerprint_length=FPCALC_LENGTH_SECONDS,
            fingerprint_algorithm=FPCALC_ALGORITHM,
        ),
    ]
    theirs = [
        make_track(
            duration=200,
            file_size=2_000_000,
            fingerprint=fingerprint,
            fingerprint_length=FPCALC_LENGTH_SECONDS,
            fingerprint_algorithm=FPCALC_ALGORITHM,
        ),
    ]
    result = match_collections(mine, theirs)

    assert result.upgrade_available == []
    assert len(result.needs_review) == 1
    assert len(result.needs_review[0].candidates) == 2


def test_the_fuzzy_tier_still_runs_when_no_fingerprint_answers(make_track):
    mine = [
        make_track(duration=200, file_size=1_000_000),
    ]
    theirs = [
        make_track(duration=200, file_size=4_000_000),
    ]
    result = match_collections(mine, theirs)

    assert len(result.missing) == 0
    assert len(result.already_have) + len(result.upgrade_available) == 1


def test_a_consumed_track_is_not_a_fingerprint_candidate(make_track, fake_fingerprint):
    fingerprint = pack_fingerprint(fake_fingerprint(7, 200))
    mine = [
        make_track(
            duration=200,
            file_size=1_000_000,
            file_hash="hash1",
            fingerprint=fingerprint,
            format="MP3",
        ),
        make_track(duration=200, file_size=3_000_000, fingerprint=fingerprint),
    ]
    theirs = [
        make_track(
            duration=200,
            file_size=1_000_000,
            file_hash="hash1",
            format="FLAC",
        ),
        make_track(
            duration=200,
            file_size=4_000_000,
            fingerprint=fingerprint,
        ),
    ]
    result = match_collections(mine, theirs)

    assert len(result.needs_review) == 0


def test_the_hash_tier_still_wins_first(make_track, fake_fingerprint):
    fingerprint = pack_fingerprint(fake_fingerprint(8, 200))
    mine = [
        make_track(
            duration=200,
            file_size=1_000_000,
            file_hash="hash1",
            fingerprint=fingerprint,
        ),
    ]
    theirs = [
        make_track(
            duration=200,
            file_size=1_000_000,
            file_hash="hash1",
            fingerprint=fingerprint,
        ),
    ]
    result = match_collections(mine, theirs)

    assert len(result.already_have) == 1
    assert result.needs_review == []


def test_a_computed_fingerprint_is_stored_on_the_track(
    make_track, fake_fingerprint, monkeypatch
):
    # Both sides start with an empty column, so both have to be computed. The
    # matcher caches onto the objects and the calling endpoint commits them,
    # exactly as it does for file_hash — so a value left unset here is a file
    # that fpcalc decodes again on every future diff, forever.
    #
    # Patch matching.compute_fingerprint, not fingerprinting's. matching.py
    # imported the name into its own module and holds its own reference, so a
    # patch on the original leaves that reference alone and the real fpcalc
    # runs.
    values = fake_fingerprint(20, 200)
    monkeypatch.setattr("matching.compute_fingerprint", lambda path: values)

    mine = [make_track(duration=200, file_size=1_000_000, format="MP3")]
    theirs = [make_track(duration=200, file_size=4_000_000, format="FLAC")]
    result = match_collections(mine, theirs)

    assert len(result.upgrade_available) == 1
    assert mine[0].fingerprint == pack_fingerprint(values)
    assert theirs[0].fingerprint == pack_fingerprint(values)


def test_the_fingerprint_count_counts_only_the_files_fpcalc_read(
    make_track, fake_fingerprint, monkeypatch
):
    # The counter is a cost signal, so it must track subprocess calls and
    # nothing else. Three distinct files reach fpcalc here, and the shared
    # candidate of mine is looked up twice — once per track of theirs — so a
    # counter that rose for a cache hit would report four.
    #
    # The broken file is counted even though it answers None. fpcalc ran and
    # spent the time, which is the whole thing the number exists to explain.
    #
    # Their tags are blank so the fuzzy tier consumes nothing, which is what
    # keeps the candidate of mine reachable for the second track of theirs.
    def stub(path):
        return None if path == "/mine/broken.mp3" else fake_fingerprint(30, 200)

    monkeypatch.setattr("matching.compute_fingerprint", stub)

    mine = [
        make_track(
            duration=200,
            file_size=1_000_000,
            file_path="/mine/broken.mp3",
            file_name="broken.mp3",
        )
    ]
    theirs = [
        make_track(
            duration=200,
            file_size=4_000_000,
            file_path="/theirs/a.mp3",
            title=None,
            artist=None,
        ),
        make_track(
            duration=200,
            file_size=5_000_000,
            file_path="/theirs/b.mp3",
            title=None,
            artist=None,
        ),
    ]
    events = []
    match_collections(mine, theirs, on_progress=events.append)

    # Read from the last frame rather than from the run object, because the
    # number the user sees is the one that travelled through DiffProgress.
    # A counter that rose correctly but was reported as a constant would
    # satisfy any assertion made against the matcher's internals.
    assert events[-1].fingerprinted_count == 3


def test_an_unreadable_file_is_not_fingerprinted_twice(
    make_track, fake_fingerprint, monkeypatch
):
    # One track of mine that fpcalc cannot read, and two tracks of theirs that
    # both reach it as a duration candidate. The negative answer has to be
    # remembered: without it the matcher starts a subprocess for that file
    # once per track of theirs, and a real collection has thousands.
    #
    # Their tags are blank on purpose. With the default tags, the fuzzy tier
    # pairs the first track of theirs with the broken file and consumes it, so
    # the second track never reaches it as a candidate and the second lookup
    # this test is about never happens. Blank tags send both to missing
    # without consuming anything, which keeps the candidate available twice.
    calls = []

    def unreadable_mine(path):
        calls.append(path)
        return None if path == "/mine/broken.mp3" else fake_fingerprint(21, 200)

    monkeypatch.setattr("matching.compute_fingerprint", unreadable_mine)

    mine = [
        make_track(
            duration=200,
            file_size=1_000_000,
            file_path="/mine/broken.mp3",
            file_name="broken.mp3",
        )
    ]
    theirs = [
        make_track(
            duration=200,
            file_size=4_000_000,
            file_path="/theirs/a.mp3",
            title=None,
            artist=None,
        ),
        make_track(
            duration=200,
            file_size=5_000_000,
            file_path="/theirs/b.mp3",
            title=None,
            artist=None,
        ),
    ]
    match_collections(mine, theirs)

    assert calls.count("/mine/broken.mp3") == 1


def test_a_fingerprint_mismatch_beats_a_matching_tag(make_track, fake_fingerprint):
    # The remaster case, and the one Phase 5 exists to stop. Same artist, same
    # title, a length inside the tolerance: the tag tier would pair these
    # confidently. The audio says they are different recordings.
    #
    # Theirs is FLAC against my MP3 on purpose. That makes the un-fixed
    # outcome upgrade_available, which with the delete action destroys my
    # file. With two MP3s the tag tier would land on already_have instead —
    # harmless, and the assertions below would pass either way.
    fingerprint1 = pack_fingerprint(fake_fingerprint(10, 200))
    fingerprint2 = pack_fingerprint(fake_fingerprint(11, 200))
    mine = [
        make_track(
            format="MP3",
            duration=200,
            file_size=1_000_000,
            title="A Title",
            artist="An Artist",
            fingerprint=fingerprint1,
            fingerprint_length=FPCALC_LENGTH_SECONDS,
            fingerprint_algorithm=FPCALC_ALGORITHM,
        ),
    ]
    theirs = [
        make_track(
            format="FLAC",
            duration=201,
            file_size=4_000_000,
            title="A Title",
            artist="An Artist",
            fingerprint=fingerprint2,
            fingerprint_length=FPCALC_LENGTH_SECONDS,
            fingerprint_algorithm=FPCALC_ALGORITHM,
        ),
    ]
    result = match_collections(mine, theirs)

    assert result.upgrade_available == []
    assert len(result.missing) == 1
    # A rejection pairs nothing, so my file stays available and unconsumed.
    assert len(result.only_in_mine) == 1


def test_without_fpcalc_the_tag_tier_decides(fake_fingerprint, make_track):
    # The same two tracks as the test above, which the audio rejects. Only the
    # flag differs, so the bucket says which tier answered: with the tier
    # skipped, the tag tier pairs them. Equal fingerprints would make both
    # tiers pair them, and the test would pass with the guard deleted.
    #
    # Stored bytes rather than a stub for compute_fingerprint. They let the
    # tier decide without fpcalc at all, so a pairing here proves the tier was
    # skipped, not that fpcalc failed.
    #
    # This pins a known weakness on purpose: without the audio, a remaster
    # with the same tags is an upgrade. The warning in the UI is what makes
    # that acceptable.
    fingerprint1 = pack_fingerprint(fake_fingerprint(10, 200))
    fingerprint2 = pack_fingerprint(fake_fingerprint(11, 200))
    mine = [
        make_track(
            format="MP3",
            duration=200,
            file_size=1_000_000,
            title="A Title",
            artist="An Artist",
            fingerprint=fingerprint1,
            fingerprint_length=FPCALC_LENGTH_SECONDS,
            fingerprint_algorithm=FPCALC_ALGORITHM,
        ),
    ]
    theirs = [
        make_track(
            format="FLAC",
            duration=201,
            file_size=4_000_000,
            title="A Title",
            artist="An Artist",
            fingerprint=fingerprint2,
            fingerprint_length=FPCALC_LENGTH_SECONDS,
            fingerprint_algorithm=FPCALC_ALGORITHM,
        ),
    ]
    result = match_collections(mine, theirs, fingerprints_available=False)

    assert len(result.upgrade_available) == 1
    assert result.rejected == []
    assert result.fingerprints_available is False


def test_a_rejection_records_the_file_it_was_compared_against(
    make_track, fake_fingerprint
):
    fingerprint1 = pack_fingerprint(fake_fingerprint(12, 200))
    fingerprint2 = pack_fingerprint(fake_fingerprint(13, 200))
    mine = [
        make_track(
            format="MP3",
            duration=200,
            file_size=1_000_000,
            title="A Title",
            artist="An Artist",
            fingerprint=fingerprint1,
            fingerprint_length=FPCALC_LENGTH_SECONDS,
            fingerprint_algorithm=FPCALC_ALGORITHM,
        ),
    ]
    theirs = [
        make_track(
            format="FLAC",
            duration=201,
            file_size=4_000_000,
            title="A Title",
            artist="An Artist",
            fingerprint=fingerprint2,
            fingerprint_length=FPCALC_LENGTH_SECONDS,
            fingerprint_algorithm=FPCALC_ALGORITHM,
        ),
    ]
    result = match_collections(mine, theirs)

    (rejection,) = result.rejected
    assert rejection.mine is mine[0]
    assert rejection.theirs is theirs[0]


# Uniform frames, so the error rate is arithmetic rather than a measurement:
# it is differing_bits / (32 * frames), and with every frame carrying the same
# pattern that reduces to bits/32 at every offset in the search.
#
# fake_fingerprint cannot serve these two. Two random lists land near 0.5 and
# within a few thousandths of each other, so neither the exact value nor which
# of two candidates is closer can be written down in advance.
#
# Five bits is the smallest whole number that clears the 0.15 threshold. Four
# would score 0.125 and be a *match*, which turns the test into one about
# pairing rather than about rejection.
QUIET_FINGERPRINT = [0] * 200
NEAR_MISS_FINGERPRINT = [0b11111] * 200  # 5/32 = 0.15625, just over
FAR_MISS_FINGERPRINT = [0b1111111] * 200  # 7/32 = 0.21875


def test_a_rejection_records_its_error_rate(make_track):
    # The exact rate, not merely a positive number. "> 0.0" passes against a
    # placeholder, against the wrong candidate's rate, and against a rate read
    # from the wrong end of the comparison.
    mine = [
        make_track(
            format="MP3",
            duration=200,
            file_size=1_000_000,
            fingerprint=pack_fingerprint(NEAR_MISS_FINGERPRINT),
            fingerprint_length=FPCALC_LENGTH_SECONDS,
            fingerprint_algorithm=FPCALC_ALGORITHM,
        ),
    ]
    theirs = [
        make_track(
            format="FLAC",
            duration=201,
            file_size=4_000_000,
            fingerprint=pack_fingerprint(QUIET_FINGERPRINT),
            fingerprint_length=FPCALC_LENGTH_SECONDS,
            fingerprint_algorithm=FPCALC_ALGORITHM,
        ),
    ]
    result = match_collections(mine, theirs)

    (rejection,) = result.rejected
    assert rejection.error_rate == pytest.approx(5 / 32)


def test_the_closest_candidate_is_the_one_recorded(make_track):
    # Two candidates at 0.15625 and 0.21875. Both are rejected, so the choice
    # between them is the only thing this test can be about — which is why it
    # asserts on rejection.mine. An assertion naming only theirs would pass
    # whichever candidate the code kept.
    near = make_track(
        format="MP3",
        duration=200,
        file_size=1_000_000,
        file_name="near.mp3",
        fingerprint=pack_fingerprint(NEAR_MISS_FINGERPRINT),
        fingerprint_length=FPCALC_LENGTH_SECONDS,
        fingerprint_algorithm=FPCALC_ALGORITHM,
    )
    far = make_track(
        format="MP3",
        duration=200,
        file_size=2_000_000,
        file_name="far.mp3",
        fingerprint=pack_fingerprint(FAR_MISS_FINGERPRINT),
        fingerprint_length=FPCALC_LENGTH_SECONDS,
        fingerprint_algorithm=FPCALC_ALGORITHM,
    )
    theirs = [
        make_track(
            format="FLAC",
            duration=202,
            file_size=4_000_000,
            fingerprint=pack_fingerprint(QUIET_FINGERPRINT),
            fingerprint_length=FPCALC_LENGTH_SECONDS,
            fingerprint_algorithm=FPCALC_ALGORITHM,
        ),
    ]
    # far first, and that order is load-bearing. Candidates arrive in the order
    # tracks_mine gives them, so with near first the code could take the head
    # of the list and still look right — a mutation replacing min() with
    # candidates[0] survives that arrangement and fails this one.
    result = match_collections([far, near], theirs)

    (rejection,) = result.rejected
    assert rejection.mine is near
    assert rejection.error_rate == pytest.approx(5 / 32)


def test_a_track_missing_for_any_other_reason_is_not_recorded(
    make_track, fake_fingerprint
):
    fingerprint = pack_fingerprint(fake_fingerprint(19, 200))
    mine = [
        make_track(
            format="MP3",
            duration=200,
            file_size=1_000_000,
            title="A Title",
            artist="An Artist",
            fingerprint=fingerprint,
            fingerprint_length=FPCALC_LENGTH_SECONDS,
            fingerprint_algorithm=FPCALC_ALGORITHM,
        ),
    ]
    theirs = [
        make_track(
            format="FLAC",
            duration=203,
            file_size=4_000_000,
            title="A Title",
            artist="An Artist",
            fingerprint=fingerprint,
            fingerprint_length=FPCALC_LENGTH_SECONDS,
            fingerprint_algorithm=FPCALC_ALGORITHM,
        ),
    ]
    result = match_collections(mine, theirs)

    assert result.rejected == []


def test_a_candidate_that_cannot_be_fingerprinted_still_reaches_the_tag_tier(
    make_track, fake_fingerprint, monkeypatch
):
    # The other half of "not comparable". The short-file case is covered by
    # test_same_size_different_content_no_hash_match, where both fingerprints
    # exist and compare_fingerprints declines on length. Here the candidate of
    # mine has no fingerprint at all, so the first condition in the comparable
    # filter is what has to catch it.
    #
    # Without a test for this the two conditions in that comprehension are not
    # separately defended: every mutation against either one was killed by the
    # short-file test alone, which would have gone on passing if the readable
    # check were deleted outright.
    #
    # Tags match and the durations are inside the tolerance, so a tier that
    # declines correctly hands these to the tag tier and gets an upgrade. A
    # tier that mistook "unreadable" for "different" would report missing.
    def unreadable_mine(path):
        return None if path == "/mine/broken.mp3" else fake_fingerprint(12, 200)

    monkeypatch.setattr("matching.compute_fingerprint", unreadable_mine)

    mine = [
        make_track(
            format="MP3",
            duration=200,
            file_size=1_000_000,
            file_path="/mine/broken.mp3",
            file_name="broken.mp3",
            title="A Title",
            artist="An Artist",
        ),
    ]
    theirs = [
        make_track(
            format="FLAC",
            duration=201,
            file_size=4_000_000,
            file_path="/theirs/good.flac",
            file_name="good.flac",
            title="A Title",
            artist="An Artist",
        ),
    ]
    result = match_collections(mine, theirs)

    assert len(result.upgrade_available) == 1
    assert result.missing == []
    # And nothing may be recorded as rejected. There are two empty-list guards
    # in the tier and they mean different things: no candidate of a plausible
    # length, which the duration test above covers, and a candidate that could
    # not be compared, which is this one. A track nothing was measured against
    # must never claim the audio disagreed.
    assert result.rejected == []


def test_a_refused_candidate_does_not_hide_an_uncomparable_one(
    make_track, fake_fingerprint, monkeypatch
):
    # broken.mp3 is the real match, but fpcalc cannot read it. other.mp3 is
    # readable, the same length, and different audio. A tier that refuses
    # other.mp3 and stops never lets the tag tier see broken.mp3, and
    # good.flac is imported as a duplicate of a file already owned.
    #
    # FLAC against MP3 so the correct outcome is an upgrade the assertion can
    # name. "is broken" and not only the count: which file of mine it paired
    # with is the whole question.
    monkeypatch.setattr("matching.compute_fingerprint", lambda path: None)

    mine = [
        make_track(
            format="MP3",
            duration=200,
            file_size=1_000_000,
            file_path="/mine/broken.mp3",
            file_name="broken.mp3",
            title="A Title",
            artist="An Artist",
        ),
        make_track(
            format="MP3",
            duration=200,
            file_size=2_000_000,
            file_path="/mine/other.mp3",
            file_name="other.mp3",
            title="Some Other Title",
            artist="Some Other Artist",
            fingerprint=pack_fingerprint(fake_fingerprint(1, 200)),
            fingerprint_length=FPCALC_LENGTH_SECONDS,
            fingerprint_algorithm=FPCALC_ALGORITHM,
        ),
    ]
    theirs = [
        make_track(
            format="FLAC",
            duration=201,
            file_size=4_000_000,
            file_path="/theirs/good.flac",
            file_name="good.flac",
            title="A Title",
            artist="An Artist",
            fingerprint=pack_fingerprint(fake_fingerprint(2, 200)),
            fingerprint_length=FPCALC_LENGTH_SECONDS,
            fingerprint_algorithm=FPCALC_ALGORITHM,
        ),
    ]
    broken = mine[0]
    result = match_collections(mine, theirs)

    assert len(result.upgrade_available) == 1
    assert result.upgrade_available[0].mine is broken
    assert result.missing == []


def test_the_tag_tier_never_pairs_a_refused_candidate(
    make_track, fake_fingerprint, monkeypatch
):
    # The trap in the obvious fix. other.mp3 carries good.flac's tags, so a
    # tier that simply declined would hand it to the tag tier, which would
    # pair them — the pairing the audio refused, and with FLAC against MP3 an
    # upgrade the delete action turns into a deletion. broken.mp3 has other
    # tags, so with other.mp3 kept out there is nothing left to pair.
    #
    # rejected must stay empty. The audio judged only one of the two
    # candidates, so "audio differs" would claim more than was measured.
    def unreadable_mine(path):
        return None if path == "/mine/broken.mp3" else fake_fingerprint(1, 200)

    monkeypatch.setattr("matching.compute_fingerprint", unreadable_mine)

    mine = [
        make_track(
            format="MP3",
            duration=200,
            file_size=1_000_000,
            file_path="/mine/broken.mp3",
            file_name="broken.mp3",
            title="Some Other Title",
            artist="Some Other Artist",
        ),
        make_track(
            format="MP3",
            duration=200,
            file_size=2_000_000,
            file_path="/mine/other.mp3",
            file_name="other.mp3",
            title="A Title",
            artist="An Artist",
            fingerprint=pack_fingerprint(FAR_MISS_FINGERPRINT),
            fingerprint_length=FPCALC_LENGTH_SECONDS,
            fingerprint_algorithm=FPCALC_ALGORITHM,
        ),
    ]
    theirs = [
        make_track(
            format="FLAC",
            duration=201,
            file_size=4_000_000,
            file_path="/theirs/good.flac",
            file_name="good.flac",
            title="A Title",
            artist="An Artist",
            fingerprint=pack_fingerprint(QUIET_FINGERPRINT),
            fingerprint_length=FPCALC_LENGTH_SECONDS,
            fingerprint_algorithm=FPCALC_ALGORITHM,
        ),
    ]

    result = match_collections(mine, theirs)

    assert result.upgrade_available == []
    assert result.rejected == []
    assert len(result.missing) == 1


def test_a_refusal_does_not_reserve_the_candidate_for_the_diff(
    make_track, fake_fingerprint, monkeypatch
):
    # refused belongs to one track of theirs, not to the diff. good.flac
    # refuses other.mp3, and broken.mp3 cannot be compared, so the tier
    # declines. nice.flac is then an exact fingerprint match for other.mp3 and
    # must still get it. Add the refusal to consumed instead and nice.flac
    # finds other.mp3 already taken, with nothing anywhere to say why.
    #
    # The order of theirs is load-bearing: good.flac has to refuse other.mp3
    # before nice.flac reaches it.
    fingerprint = fake_fingerprint(1, 200)

    def unreadable_mine(path):
        return None if path == "/mine/broken.mp3" else fingerprint

    monkeypatch.setattr("matching.compute_fingerprint", unreadable_mine)

    mine = [
        make_track(
            format="MP3",
            duration=200,
            file_size=1_000_000,
            file_path="/mine/broken.mp3",
            file_name="broken.mp3",
            title="A Title",
            artist="An Artist",
        ),
        make_track(
            format="MP3",
            duration=200,
            file_size=2_000_000,
            file_path="/mine/other.mp3",
            file_name="other.mp3",
            title="B Title",
            artist="B Artist",
        ),
    ]
    theirs = [
        make_track(
            format="FLAC",
            duration=201,
            file_size=3_000_000,
            file_path="/theirs/good.flac",
            file_name="good.flac",
            title="Some Other Title",
            artist="Some Other Artist",
            fingerprint=pack_fingerprint(QUIET_FINGERPRINT),
            fingerprint_length=FPCALC_LENGTH_SECONDS,
            fingerprint_algorithm=FPCALC_ALGORITHM,
        ),
        make_track(
            format="FLAC",
            duration=201,
            file_size=4_000_000,
            file_path="/theirs/nice.flac",
            file_name="nice.flac",
            title="Title",
            artist="Artist",
        ),
    ]

    result = match_collections(mine, theirs)

    assert len(result.upgrade_available) == 1
    assert result.upgrade_available[0].mine is mine[1]
    assert result.upgrade_available[0].theirs is theirs[1]


def test_a_fingerprint_from_another_algorithm_is_recomputed(
    make_track, fake_fingerprint, monkeypatch
):
    values = fake_fingerprint(22, 200)
    monkeypatch.setattr("matching.compute_fingerprint", lambda path: values)

    mine = [
        make_track(
            format="MP3",
            duration=200,
            file_size=1_000_000,
            fingerprint=pack_fingerprint(fake_fingerprint(23, 200)),
            fingerprint_length=FPCALC_LENGTH_SECONDS,
            fingerprint_algorithm=17,
        ),
    ]
    theirs = [
        make_track(
            format="FLAC",
            duration=200,
            file_size=4_000_000,
            fingerprint=pack_fingerprint(values),
            fingerprint_length=FPCALC_LENGTH_SECONDS,
            fingerprint_algorithm=FPCALC_ALGORITHM,
        ),
    ]
    result = match_collections(mine, theirs)

    assert len(result.upgrade_available) == 1
    assert mine[0].fingerprint == pack_fingerprint(values)


def test_a_fingerprint_from_another_length_is_recomputed(
    make_track, fake_fingerprint, monkeypatch
):
    values = fake_fingerprint(24, 200)
    monkeypatch.setattr("matching.compute_fingerprint", lambda path: values)

    mine = [
        make_track(
            format="MP3",
            duration=200,
            file_size=1_000_000,
            fingerprint=pack_fingerprint(fake_fingerprint(25, 200)),
            fingerprint_length=FPCALC_LENGTH_SECONDS + 1,
            fingerprint_algorithm=FPCALC_ALGORITHM,
        ),
    ]
    theirs = [
        make_track(
            format="FLAC",
            duration=200,
            file_size=4_000_000,
            fingerprint=pack_fingerprint(values),
            fingerprint_length=FPCALC_LENGTH_SECONDS,
            fingerprint_algorithm=FPCALC_ALGORITHM,
        ),
    ]
    result = match_collections(mine, theirs)

    assert len(result.upgrade_available) == 1
    assert mine[0].fingerprint == pack_fingerprint(values)


def test_a_fingerprint_from_the_current_producer_is_reused(
    make_track, fake_fingerprint, monkeypatch
):
    values = fake_fingerprint(26, 200)
    monkeypatch.setattr("matching.compute_fingerprint", lambda path: values)

    mine = [
        make_track(
            format="MP3",
            duration=200,
            file_size=1_000_000,
            fingerprint=pack_fingerprint(values),
            fingerprint_length=FPCALC_LENGTH_SECONDS,
            fingerprint_algorithm=FPCALC_ALGORITHM,
        ),
    ]
    theirs = [
        make_track(
            format="FLAC",
            duration=200,
            file_size=4_000_000,
            fingerprint=pack_fingerprint(values),
            fingerprint_length=FPCALC_LENGTH_SECONDS,
            fingerprint_algorithm=FPCALC_ALGORITHM,
        ),
    ]
    events = []
    match_collections(mine, theirs, on_progress=events.append)

    assert events[-1].fingerprinted_count == 0


def test_a_recomputed_fingerprint_overwrites_the_stale_one(
    make_track, fake_fingerprint, monkeypatch
):
    # The producer is the point of this test, not the bytes. New bytes stored
    # without their producer are judged stale by the next diff, which
    # recomputes and stores them producer-less again — every fingerprint
    # decoded on every diff, for good, while the bytes look perfect.
    #
    # It starts from bytes with no producer at all, which is what every row
    # written before these columns existed looks like. That is also the only
    # starting point that tests both assignments: a stale row already
    # carrying the current algorithm passes an algorithm assertion whether or
    # not the recompute wrote it, because a value that was already right
    # cannot prove it was set.
    values = fake_fingerprint(27, 200)
    monkeypatch.setattr("matching.compute_fingerprint", lambda path: values)

    mine = [
        make_track(
            format="MP3",
            duration=200,
            file_size=1_000_000,
            fingerprint=pack_fingerprint(fake_fingerprint(28, 200)),
            fingerprint_length=None,
            fingerprint_algorithm=None,
        ),
    ]
    theirs = [
        make_track(
            format="FLAC",
            duration=200,
            file_size=4_000_000,
            fingerprint=pack_fingerprint(values),
            fingerprint_length=FPCALC_LENGTH_SECONDS,
            fingerprint_algorithm=FPCALC_ALGORITHM,
        ),
    ]
    result = match_collections(mine, theirs)

    assert len(result.upgrade_available) == 1
    assert mine[0].fingerprint == pack_fingerprint(values)
    assert mine[0].fingerprint_length == FPCALC_LENGTH_SECONDS
    assert mine[0].fingerprint_algorithm == FPCALC_ALGORITHM


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


# Answers by path, with None for a file the filesystem refuses. Square
# brackets, not .get: a read of a path that a test did not list raises
# KeyError, so an unexpected read fails the test.
#
# The tests below pass fingerprints_available=False. They concern the hash
# tier only, and fpcalc on these fake paths adds time and a warning per call.
def fake_compute_file_hash(path: str) -> str | None:
    answers = {
        "/fake/path.mp3": "hash_123456789",
        "/fake/another_path.mp3": "hash_987654321",
        "/fake/none.mp3": None,
        "/fake/none.flac": None,
        "/fake/ninguno.mp3": None,
    }
    return answers[path]


def test_an_unreadable_file_of_theirs_reaches_the_tag_tier(monkeypatch, make_track):
    monkeypatch.setattr("matching.compute_file_hash", fake_compute_file_hash)
    mine = [
        make_track(
            format="MP3",
            file_path="/fake/path.mp3",
            file_name="one.mp3",
            file_size=1_000_000,
        )
    ]
    theirs = [
        make_track(
            format="FLAC",
            file_path="/fake/none.flac",
            file_name="none.flac",
            file_size=1_000_000,
        )
    ]
    result = match_collections(mine, theirs, fingerprints_available=False)

    # An upgrade, not only "no exception". Only the tag tier can pair these
    # two, so a matcher that sends the track to missing fails here.
    assert len(result.upgrade_available) == 1
    assert result.upgrade_available[0].theirs is theirs[0]


def test_two_unreadable_files_of_one_size_are_not_identical(monkeypatch, make_track):
    monkeypatch.setattr("matching.compute_file_hash", fake_compute_file_hash)

    # Different titles, so the tag tier cannot pair the two. With equal tags
    # it puts them in already_have too, and the test cannot see the bug.
    mine = [
        make_track(
            file_path="/fake/none.mp3",
            file_size=1_000_000,
            title="A Title",
            artist="An Artist",
        )
    ]
    theirs = [
        make_track(
            file_path="/fake/ninguno.mp3",
            file_size=1_000_000,
            title="Another Title",
            artist="Another Artist",
        )
    ]
    result = match_collections(mine, theirs, fingerprints_available=False)

    assert len(result.already_have) == 0
    assert len(result.missing) == 1
    assert len(result.only_in_mine) == 1
    assert result.missing[0] is theirs[0]
    assert result.only_in_mine[0] is mine[0]


def test_an_unreadable_file_of_mine_is_opened_once_per_diff(monkeypatch, make_track):
    calls = []

    def fake_compute_file_hash_with_append(path: str) -> str | None:
        answers = {
            "/fake/path.mp3": "hash_123456789",
            "/fake/another_path.mp3": "hash_987654321",
            "/fake/none.mp3": None,
            "/fake/none.flac": None,
        }
        calls.append(path)
        return answers[path]

    monkeypatch.setattr(
        "matching.compute_file_hash", fake_compute_file_hash_with_append
    )
    # Titles different from mine. With equal tags, the tag tier pairs the
    # first track of theirs with mine and consumes it. The loop then skips
    # mine for the second track, and the test passes without hash_failures.
    mine = [
        make_track(
            file_path="/fake/none.mp3",
            file_size=1_000_000,
            title="A Title",
            artist="An Artist",
        )
    ]
    theirs = [
        make_track(
            file_path="/fake/path.mp3",
            file_size=1_000_000,
            title="Another Title",
            artist="Another Artist",
        ),
        make_track(
            file_path="/fake/another_path.mp3",
            file_size=1_000_000,
            title="Yet Another Title",
            artist="Yet Another Artist",
        ),
    ]

    match_collections(mine, theirs, fingerprints_available=False)

    # == 1, never <= 1. A stub patched on the wrong name gets no paths, and
    # <= 1 passes with zero calls.
    assert calls.count(mine[0].file_path) == 1


def test_a_failed_hash_is_not_counted_as_read(monkeypatch, make_track):
    monkeypatch.setattr("matching.compute_file_hash", fake_compute_file_hash)
    mine = [
        make_track(
            file_path="/fake/none.mp3",
            file_size=1_000_000,
            title="A Title",
            artist="An Artist",
        )
    ]
    theirs = [
        make_track(
            file_path="/fake/path.mp3",
            file_size=1_000_000,
            title="Another Title",
            artist="Another Artist",
        )
    ]

    events = []
    match_collections(
        mine, theirs, on_progress=events.append, fingerprints_available=False
    )

    # One file was read, the file of theirs. A count that increased before
    # the None result was known gives 2.
    assert events[-1].hashed_count == 1


def test_a_stored_hash_of_theirs_still_pairs_by_hash(monkeypatch, make_track):
    monkeypatch.setattr("matching.compute_file_hash", fake_compute_file_hash)
    # Paths that the stub does not list, so any read raises KeyError: a stored
    # hash must cause no read. Different titles, so only the hash tier can
    # pair the two. With equal tags, the tag tier also puts them in
    # already_have, and the test passes when the hash tier skips them.
    mine = [
        make_track(
            file_path="/fake/stored_mine.mp3",
            file_size=1_000_000,
            file_hash="hash_stored",
            title="A Title",
            artist="An Artist",
        )
    ]
    theirs = [
        make_track(
            file_path="/fake/stored_theirs.mp3",
            file_size=1_000_000,
            file_hash="hash_stored",
            title="Another Title",
            artist="Another Artist",
        )
    ]
    result = match_collections(mine, theirs, fingerprints_available=False)

    # Every diff after the first sees stored hashes, because the endpoint
    # commits them. So this is the ordinary case, not an edge case.
    assert len(result.already_have) == 1
    assert result.already_have[0].mine is mine[0]
    assert result.already_have[0].theirs is theirs[0]


def test_a_file_that_cannot_be_hashed_is_listed(make_track, monkeypatch):
    monkeypatch.setattr("matching.compute_file_hash", fake_compute_file_hash)
    mine = [
        make_track(
            file_path="/fake/path.mp3",
            file_size=1_000_000,
            title="A Title",
            artist="An Artist",
        )
    ]
    theirs = [
        make_track(
            file_path="/fake/none.mp3",
            file_size=1_000_000,
            title="Another Title",
            artist="Another Artist",
        )
    ]
    result = match_collections(mine, theirs, fingerprints_available=False)

    assert result.unreadable_files == [theirs[0].file_path]


def test_a_file_that_cannot_be_fingerprinted_is_listed(
    make_track, monkeypatch, fake_fingerprint
):
    def fake_compute_fingerprint(path):
        return fake_fingerprint(1) if path == "/fake/theirs.mp3" else None

    monkeypatch.setattr("matching.compute_fingerprint", fake_compute_fingerprint)
    mine = [
        make_track(
            file_path="/fake/mine.mp3",
            file_size=1_000_000,
            duration=200,
            title="A Title",
            artist="An Artist",
        )
    ]
    theirs = [
        make_track(
            file_path="/fake/theirs.mp3",
            file_size=2_000_000,
            duration=200,
            title="Another Title",
            artist="Another Artist",
        )
    ]
    result = match_collections(mine, theirs)

    assert result.unreadable_files == [mine[0].file_path]


def test_a_file_that_fails_both_tiers_is_listed_once(
    make_track, monkeypatch, fake_fingerprint
):
    def fake_compute_fingerprint(path):
        return fake_fingerprint(1) if path == "/fake/path.mp3" else None

    monkeypatch.setattr("matching.compute_fingerprint", fake_compute_fingerprint)
    monkeypatch.setattr("matching.compute_file_hash", fake_compute_file_hash)
    mine = [
        make_track(
            file_path="/fake/path.mp3",
            file_size=1_000_000,
            duration=200,
            title="A Title",
            artist="An Artist",
        )
    ]
    theirs = [
        make_track(
            file_path="/fake/none.mp3",
            file_size=1_000_000,
            duration=200,
            title="Another Title",
            artist="Another Artist",
        )
    ]
    result = match_collections(mine, theirs)

    assert result.unreadable_files == [theirs[0].file_path]


def test_a_file_that_was_never_read_is_not_listed(make_track):
    mine = [
        make_track(
            file_path="/fake/path.mp3",
            file_size=1_000_000,
            duration=100,
            title="A Title",
            artist="An Artist",
        )
    ]
    theirs = [
        make_track(
            file_path="/fake/none.mp3",
            file_size=2_000_000,
            duration=200,
            title="Another Title",
            artist="Another Artist",
        )
    ]
    result = match_collections(mine, theirs)

    assert result.unreadable_files == []


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


def test_an_equal_wav_is_not_an_upgrade_over_a_flac(make_track):
    mine = make_track(format="FLAC", bit_depth=16, sample_rate=44100, bit_rate=900000)
    theirs = make_track(format="WAV", bit_depth=16, sample_rate=44100, bit_rate=1411200)

    result = classify_pairing(mine_track=mine, theirs_track=theirs)

    assert result == Bucket.ALREADY_HAVE


def test_a_higher_bit_depth_is_an_upgrade(make_track):
    mine = make_track(format="FLAC", bit_depth=16, sample_rate=44100, bit_rate=1000000)
    theirs = make_track(format="FLAC", bit_depth=24, sample_rate=44100, bit_rate=900000)

    result = classify_pairing(mine_track=mine, theirs_track=theirs)

    assert result == Bucket.UPGRADE_AVAILABLE


def test_a_higher_sample_rate_is_an_upgrade(make_track):
    mine = make_track(format="FLAC", bit_depth=16, sample_rate=44100, bit_rate=1000000)
    theirs = make_track(format="FLAC", bit_depth=16, sample_rate=96000, bit_rate=900000)

    result = classify_pairing(mine_track=mine, theirs_track=theirs)

    assert result == Bucket.UPGRADE_AVAILABLE


# Both directions, because a lexicographic order fails only one of them: bit
# depth first gets the first case wrong, sample rate first gets the second.
# Theirs carries the higher bitrate in both, so the old bitrate rule would
# call either one an upgrade.
@pytest.mark.parametrize(
    "mine_bit_depth, mine_sample_rate, theirs_bit_depth, theirs_sample_rate",
    [
        (16, 96000, 24, 44100),
        (24, 44100, 16, 96000),
    ],
    ids=["more bits, lower rate", "higher rate, fewer bits"],
)
def test_a_mixed_pair_is_not_an_upgrade_in_either_direction(
    make_track, mine_bit_depth, mine_sample_rate, theirs_bit_depth, theirs_sample_rate
):
    mine = make_track(
        format="FLAC",
        bit_depth=mine_bit_depth,
        sample_rate=mine_sample_rate,
        bit_rate=900000,
    )
    theirs = make_track(
        format="FLAC",
        bit_depth=theirs_bit_depth,
        sample_rate=theirs_sample_rate,
        bit_rate=1000000,
    )

    result = classify_pairing(mine_track=mine, theirs_track=theirs)

    assert result == Bucket.ALREADY_HAVE


# One None per case, and every other value makes theirs the better file: 24
# bits over 16, 96 kHz over 44.1 kHz, and the higher bitrate. So the missing
# value is the only thing that can stop the upgrade. With values that already
# lose on their own, reading None as 0 passes every case, and Python's `and`
# stops before it ever compares the None.
@pytest.mark.parametrize(
    "mine_bit_depth, mine_sample_rate, theirs_bit_depth, theirs_sample_rate",
    [
        (None, 44100, 24, 96000),
        (16, None, 24, 96000),
        (16, 44100, None, 96000),
        (16, 44100, 24, None),
        (0, 44100, 24, 96000),
        (16, 0, 24, 96000),
    ],
    ids=[
        "mine: no bit depth",
        "mine: no sample rate",
        "theirs: no bit depth",
        "theirs: no sample rate",
        "mine: bit depth 0",
        "mine: sample rate 0",
    ],
)
def test_a_missing_value_is_not_an_upgrade(
    make_track, mine_bit_depth, mine_sample_rate, theirs_bit_depth, theirs_sample_rate
):
    mine = make_track(
        format="FLAC",
        bit_depth=mine_bit_depth,
        sample_rate=mine_sample_rate,
        bit_rate=900000,
    )
    theirs = make_track(
        format="FLAC",
        bit_depth=theirs_bit_depth,
        sample_rate=theirs_sample_rate,
        bit_rate=1000000,
    )

    result = classify_pairing(mine_track=mine, theirs_track=theirs)

    assert result == Bucket.ALREADY_HAVE


def test_a_bitrate_of_zero_counts_as_unmeasured(make_track):
    mine = make_track(
        format="AAC",
        bit_rate=0,
    )
    theirs = make_track(
        format="MP3",
        bit_rate=320000,
    )

    result = classify_pairing(mine_track=mine, theirs_track=theirs)

    assert result == Bucket.ALREADY_HAVE


# Equal bit depth and sample rate, and theirs carries the higher bitrate. A
# format missing from LOSSLESS_FORMATS falls to the bitrate rule and becomes
# an upgrade here.
@pytest.mark.parametrize("fmt", ["AIFF", "TTA"])
def test_a_new_lossless_format_ties_with_flac(make_track, fmt):
    mine = make_track(format="FLAC", bit_depth=16, sample_rate=44100, bit_rate=900000)
    theirs = make_track(format=fmt, bit_depth=16, sample_rate=44100, bit_rate=1411200)

    result = classify_pairing(mine_track=mine, theirs_track=theirs)

    assert result == Bucket.ALREADY_HAVE


# Both directions, so a rank above MP3 fails the first case and a rank below
# it fails the second. Two stacked parametrize marks run every format with
# every bitrate case.
@pytest.mark.parametrize("fmt", ["OPUS", "VORBIS"])
@pytest.mark.parametrize(
    "their_bit_rate, expected",
    [(128000, Bucket.ALREADY_HAVE), (512000, Bucket.UPGRADE_AVAILABLE)],
    ids=["lower bitrate", "higher bitrate"],
)
def test_a_new_lossy_format_ranks_with_mp3(make_track, fmt, their_bit_rate, expected):
    mine = make_track(format="MP3", bit_rate=320000)
    theirs = make_track(format=fmt, bit_rate=their_bit_rate)

    result = classify_pairing(mine_track=mine, theirs_track=theirs)

    assert result == expected
