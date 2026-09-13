"""Tests for fingerprint comparison, built from hand-written integer lists.

None of the audio fixtures under tests/fixtures/ can serve this module. All
four of them produce the identical Chromaprint value, because five seconds of
a stationary tone gives about 35 frames of an unchanging spectrum. A suite
built on them would report "same recording" for every pairing and would stay
green against a comparison that returned its answer inverted.

Sizes here are written as literals rather than derived from
MIN_OVERLAP_FRAMES and MAX_OFFSET_FRAMES. Deriving them would move the test
data whenever either constant moved, so a mutation of either one could not
fail anything.
"""

import logging
import shutil
import subprocess
import types

import pytest

import fingerprinting
from fingerprinting import (
    compare_fingerprints,
    compute_fingerprint,
    fingerprints_match,
    fpcalc_available,
    pack_fingerprint,
    unpack_fingerprint,
)


def test_identical_fingerprints_have_no_error(fake_fingerprint):
    a = fake_fingerprint(1)

    assert compare_fingerprints(a, list(a)) == 0.0


def test_one_flipped_bit_is_one_bit_of_error(fake_fingerprint):
    a = fake_fingerprint(2)
    b = list(a)
    b[0] ^= 1

    # The exact fraction, not merely "small". A denominator of anything but
    # 32 bits per frame passes a "close to zero" assertion and fails this one.
    assert compare_fingerprints(a, b) == pytest.approx(1 / (32 * len(a)))


def test_negative_values_are_read_as_unsigned_32_bit():
    # What a future fpcalc printing signed integers would hand us: -1 is the
    # same 32 bits as 0xFFFFFFFF. Without the mask, Python counts the bits of
    # the absolute value and reports a difference that is not there.
    signed = [-1] * 100
    unsigned = [0xFFFFFFFF] * 100

    assert compare_fingerprints(signed, unsigned) == 0.0


def test_a_shifted_copy_is_found_by_the_offset_search(fake_fingerprint):
    # b starts 6 frames into a, so only a positive offset lines them up.
    base = fake_fingerprint(3, 220)

    assert compare_fingerprints(base, base[6:]) == 0.0


def test_the_offset_search_looks_both_ways(fake_fingerprint):
    # The mirror of the test above: a starts 6 frames into b, so the answer
    # is at a negative offset. A loop that runs 0..MAX_OFFSET_FRAMES finds
    # the previous case and misses this one, which is the whole point of
    # keeping both.
    base = fake_fingerprint(4, 220)
    a = base[6:]
    b = base

    assert compare_fingerprints(a, b) == 0.0
    assert compare_fingerprints(a, b) == compare_fingerprints(b, a)


def test_the_error_rate_divides_by_the_overlap_not_the_whole_list(fake_fingerprint):
    # One flipped bit, but the two lists only overlap by 180 frames, not the
    # 200 and 190 they are long. Dividing by either length gives a different
    # number from the right one.
    base = fake_fingerprint(13, 200)
    b = base[10:]
    b[0] ^= 1

    assert compare_fingerprints(base, b) == pytest.approx(1 / (32 * 180))


def test_a_short_overlap_cannot_win(fake_fingerprint):
    # 90-frame lists whose tail and head agree perfectly at offset 16. That
    # offset leaves an overlap of 74, below the minimum, so it must be
    # refused. Without the minimum it scores 0.0 and wins outright, and two
    # unrelated recordings are declared the same.
    a = fake_fingerprint(5, 90)
    b = fake_fingerprint(6, 90)
    a[16:] = b[:74]

    assert compare_fingerprints(a, b) > 0.3


def test_unrelated_fingerprints_are_far_apart(fake_fingerprint):
    a = fake_fingerprint(7)
    b = fake_fingerprint(8)

    assert 0.4 < compare_fingerprints(a, b) < 0.6


def test_a_fingerprint_too_short_to_compare_returns_none(fake_fingerprint):
    # 40 frames cannot reach the minimum overlap at any offset. None means
    # "no answer", which the caller must be able to tell apart from a real
    # rate of 1.0 meaning "every bit differs".
    a = fake_fingerprint(9, 40)
    b = fake_fingerprint(10, 40)

    assert compare_fingerprints(a, b) is None


def test_fingerprints_match_applies_the_threshold():
    # 4 differing bits per frame is 0.125, under the threshold. 5 is 0.15625,
    # over it. Uniform frames so the rate is the same at every offset and the
    # assertion is about the threshold alone.
    quiet = [0] * 100

    assert fingerprints_match(quiet, [0b1111] * 100) is True
    assert fingerprints_match(quiet, [0b11111] * 100) is False


def test_a_rate_exactly_on_the_threshold_counts_as_a_match():
    # Exactly 0.15, and reachable only because the arithmetic allows it: a
    # rate is differing_bits / (32 * frames), so 0.15 needs 4.8 bits per
    # frame on average, which needs a frame count divisible by 5. 80 frames
    # give 2560 bits, and 384 of them differ.
    #
    # 80-frame lists also make offset 0 the only offset with a large enough
    # overlap, so no other offset can return a lower rate and hide the
    # boundary.
    quiet = [0] * 80
    exactly_fifteen_percent = [0b11111] * 64 + [0b1111] * 16

    assert compare_fingerprints(quiet, exactly_fifteen_percent) == 0.15
    assert fingerprints_match(quiet, exactly_fifteen_percent) is True


def test_fingerprints_match_is_false_when_nothing_can_be_compared(fake_fingerprint):
    # The two lists are identical, so the only thing that can produce False
    # is the refusal to compare them at all. Two unrelated short lists would
    # pass this assertion even with the minimum-overlap guard removed, since
    # a rate near 0.5 is over the threshold anyway.
    a = fake_fingerprint(11, 40)

    assert fingerprints_match(a, list(a)) is False


SAMPLE_VALUES = [
    113680835,
    113418561,
    239248129,
    333251216,
    244251612,
    255551216,
    394845672,
    409739567,
    555556756,
    908989765,
]
SAMPLE_FINGERPRINT_LINE = "FINGERPRINT=" + ",".join(str(v) for v in SAMPLE_VALUES)


@pytest.fixture
def stub_fpcalc(monkeypatch):
    """Replace both halves of the fpcalc call, and record what it received.

    Patching `subprocess.run` alone is not enough, and the gap is silent.
    `compute_fingerprint` asks `_find_fpcalc` first, so on a machine with no
    fpcalc installed it returns None and the stub is never consulted — the
    test then passes or fails according to what is on PATH, which is the one
    property a stub exists to remove. Three tests failed exactly that way
    before this fixture existed.

    Pass `found=False` for the "fpcalc is not installed" path. The returned
    record still reports `params is None` afterwards, which is how a test
    shows that the subprocess was never started rather than started and
    ignored.
    """

    def _install(stdout="", returncode=0, stderr="", error=None, found=True):
        record = types.SimpleNamespace(params=None, kwargs=None)

        def fake_run(params, **kwargs):
            record.params = params
            record.kwargs = kwargs
            if error is not None:
                raise error
            return subprocess.CompletedProcess(
                args=params, returncode=returncode, stdout=stdout, stderr=stderr
            )

        monkeypatch.setattr(
            fingerprinting,
            "_find_fpcalc",
            lambda: "/nowhere/fpcalc" if found else None,
        )
        monkeypatch.setattr(fingerprinting.subprocess, "run", fake_run)
        return record

    return _install


def test_a_fingerprint_is_parsed_from_the_output(stub_fpcalc):
    stub_fpcalc(stdout=f"DURATION=5\n{SAMPLE_FINGERPRINT_LINE}\n")

    assert compute_fingerprint("doesntmatter.wav") == SAMPLE_VALUES


def test_the_duration_line_is_ignored(stub_fpcalc):
    # Before and after, because reading by prefix and reading by line number
    # agree when DURATION comes first and disagree here.
    stub_fpcalc(stdout=f"DURATION=5\n{SAMPLE_FINGERPRINT_LINE}\nDURATION=5\n")

    assert compute_fingerprint("doesntmatter.wav") == SAMPLE_VALUES


def test_a_missing_fpcalc_gives_none(stub_fpcalc):
    record = stub_fpcalc(stdout=f"{SAMPLE_FINGERPRINT_LINE}\n", found=False)

    assert compute_fingerprint("doesntmatter.wav") is None
    # Parseable output was waiting behind the lookup, so a None here could
    # have come from either guard. This says which one answered.
    assert record.params is None


def test_fpcalc_is_available_when_the_lookup_finds_it(stub_fpcalc):
    stub_fpcalc()

    # "is True", not a bare assert: a function that handed back the path
    # itself would pass a truthiness check.
    assert fpcalc_available() is True


def test_fpcalc_is_unavailable_when_the_lookup_finds_nothing(stub_fpcalc):
    stub_fpcalc(found=False)

    assert fpcalc_available() is False


def test_a_failed_run_gives_none(stub_fpcalc):
    # Parseable output alongside the failure, deliberately. With empty stdout
    # this test passes even when the return-code guard is deleted, because the
    # parse loop then finds no FINGERPRINT line and returns None by another
    # route. A fingerprint here leaves the guard as the only thing that can
    # produce None.
    stub_fpcalc(
        returncode=1,
        stdout=f"{SAMPLE_FINGERPRINT_LINE}\n",
        stderr="fpcalc: error: something went wrong\n",
    )

    assert compute_fingerprint("doesntmatter.wav") is None


def test_a_timeout_gives_none(stub_fpcalc):
    stub_fpcalc(error=subprocess.TimeoutExpired(cmd="fpcalc", timeout=1))

    assert compute_fingerprint("doesntmatter.wav") is None


def test_an_os_error_gives_none(stub_fpcalc):
    # The binary vanished between the PATH lookup and the call, or the drive
    # holding it went away. Distinct from a timeout and from a bad exit code.
    stub_fpcalc(error=OSError("cannot run the program"))

    assert compute_fingerprint("doesntmatter.wav") is None


def test_output_with_no_fingerprint_line_gives_none(stub_fpcalc):
    stub_fpcalc(stdout="DURATION=247\n")

    assert compute_fingerprint("doesntmatter.wav") is None


def test_a_fingerprint_that_is_not_numeric_gives_none(stub_fpcalc):
    # fpcalc exiting 0 with an unparseable fingerprint is close to
    # impossible. It is covered because int() sits on the one path where a
    # single unreadable file could otherwise raise and end a whole diff.
    stub_fpcalc(stdout="DURATION=5\nFINGERPRINT=113680835,not-a-number,239248129\n")

    assert compute_fingerprint("doesntmatter.wav") is None


# One parametrized test, because the cases differ only in what the stub
# returns, and separate copies are separate places to forget a new failure.
#
# The expected column pins the branch that each case reached. Every failure
# path writes the path and returns None, so without that column a setup
# mistake that sends every case down one branch passes all five. The return
# value is pinned as well: a warning that names the file is still wrong if a
# fingerprint comes back with it.
@pytest.mark.parametrize(
    "params, expected",
    [
        (
            {"returncode": 2, "stderr": "ERROR: unable to open file"},
            "fpcalc failed with return code",
        ),
        (
            {"error": subprocess.TimeoutExpired(cmd="fpcalc", timeout=1)},
            "fpcalc failed on",
        ),
        ({"error": OSError("cannot run the program")}, "fpcalc failed on"),
        ({"stdout": "DURATION=247\n"}, "fpcalc output did not contain a fingerprint"),
        (
            {"stdout": "DURATION=5\nFINGERPRINT=113680835,not-a-number\n"},
            "non-numeric fingerprint",
        ),
    ],
    ids=["return code", "timeout", "OSError", "no fingerprint", "not numeric"],
)
def test_every_failure_names_the_file(params, expected, stub_fpcalc, caplog):
    path = r"C:\music\Radiohead\Creep.mp3"
    with caplog.at_level(logging.WARNING):
        stub_fpcalc(**params)
        result = compute_fingerprint(path)

    assert result is None
    assert path in caplog.text
    assert expected in caplog.text


def test_the_length_is_passed_to_fpcalc(stub_fpcalc):
    record = stub_fpcalc(stdout=f"{SAMPLE_FINGERPRINT_LINE}\n")

    compute_fingerprint("doesntmatter.wav")

    # Nothing else sees these arguments. Drop -length and every other test
    # still passes, while every stored fingerprint silently changes meaning.
    assert record.params is not None
    assert "-raw" in record.params
    assert "-length" in record.params
    length_index = record.params.index("-length")
    assert record.params[length_index + 1] == str(fingerprinting.FPCALC_LENGTH_SECONDS)


def test_the_algorithm_is_passed_to_fpcalc(stub_fpcalc):
    record = stub_fpcalc(stdout=f"{SAMPLE_FINGERPRINT_LINE}\n")

    compute_fingerprint("doesntmatter.wav")

    # Dropping -algorithm changes nothing today, because 2 is fpcalc 1.6.1's
    # own default — which is exactly why it needs a test of its own. The row
    # records FPCALC_ALGORITHM beside the bytes, so if fpcalc was never told
    # to use it, a future default would write values the stored producer
    # describes wrongly. A producer fpcalc never obeyed is worse than no
    # record, because the matcher trusts it.
    assert record.params is not None
    assert "-algorithm" in record.params
    algorithm_index = record.params.index("-algorithm")
    assert record.params[algorithm_index + 1] == str(fingerprinting.FPCALC_ALGORITHM)


def test_the_run_is_given_a_timeout(stub_fpcalc):
    # Nothing else notices a missing timeout, because a stub always returns
    # at once. fpcalc on a sleeping or disconnected drive waits forever, and
    # the diff waits with it — the failure FPCALC_TIMEOUT_SECONDS exists to
    # bound, and one that no other assertion here can reach.
    record = stub_fpcalc(stdout=f"{SAMPLE_FINGERPRINT_LINE}\n")

    compute_fingerprint("doesntmatter.wav")

    assert record.kwargs["timeout"] == fingerprinting.FPCALC_TIMEOUT_SECONDS


@pytest.mark.skipif(shutil.which("fpcalc") is None, reason="fpcalc is not installed")
def test_fpcalc_reads_a_real_file(fixtures_dir):
    # The only test that starts the real program. Everything above assumes an
    # output format; this is what would notice if that assumption were wrong.
    fp = compute_fingerprint(str(fixtures_dir / "test_track.mp3"))

    assert isinstance(fp, list)
    # Not merely non-None: `all()` over an empty list is True, so a fingerprint
    # of [] would satisfy the type assertions below on its own. The 5-second
    # fixture yields about 35 frames.
    assert len(fp) > 10
    assert all(isinstance(value, int) for value in fp)


def test_a_fingerprint_survives_a_round_trip(fake_fingerprint):
    original = fake_fingerprint(12)

    packed = pack_fingerprint(original)
    unpacked = unpack_fingerprint(packed)

    assert unpacked == original


def test_an_empty_fingerprint_survives_a_round_trip():
    original: list[int] = []

    packed = pack_fingerprint(original)
    unpacked = unpack_fingerprint(packed)

    assert unpacked == original


def test_the_largest_values_survive_a_round_trip():
    # Both values have the top bit set, which is where a signed format would
    # differ from an unsigned one: read as signed, 0xFFFFFFFF is -1 and
    # 0x80000000 is -2147483648. Changing `I` to `i` in both functions still
    # round-trips those two back to themselves, so this test is about range
    # rather than about signedness — it fails on a narrower format such as
    # `H`, which cannot hold either number.
    original = [0xFFFFFFFF, 0x80000000]

    packed = pack_fingerprint(original)
    unpacked = unpack_fingerprint(packed)

    assert unpacked == original


def test_the_packed_form_is_little_endian_and_four_bytes():
    # The literal bytes, because no round trip can pin them. Flip `<` to `>`
    # in both functions and every round-trip test above still passes — pack
    # and unpack move together and agree with each other under any byte
    # order. What they cannot agree with is a row already in the database,
    # written by the previous version. This assertion is the only thing
    # standing between a format change and a column of silently misread
    # fingerprints.
    original = [0x12345678, 0x9ABCDEF0, 1]

    packed = pack_fingerprint(original)

    assert packed == b"\x78\x56\x34\x12\xf0\xde\xbc\x9a\x01\x00\x00\x00"
