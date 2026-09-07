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

import random

import pytest

from fingerprinting import compare_fingerprints, fingerprints_match


def fake_fingerprint(seed: int, frames: int = 200) -> list[int]:
    """Build a repeatable list of 32-bit values that stands in for a real one.

    Seeded rather than random, so a failure reproduces. Two different seeds
    stand in for two unrelated recordings.
    """
    rng = random.Random(seed)
    return [rng.getrandbits(32) for _ in range(frames)]


def test_identical_fingerprints_have_no_error():
    a = fake_fingerprint(1)

    assert compare_fingerprints(a, list(a)) == 0.0


def test_one_flipped_bit_is_one_bit_of_error():
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


def test_a_shifted_copy_is_found_by_the_offset_search():
    # b starts 6 frames into a, so only a positive offset lines them up.
    base = fake_fingerprint(3, 220)

    assert compare_fingerprints(base, base[6:]) == 0.0


def test_the_offset_search_looks_both_ways():
    # The mirror of the test above: a starts 6 frames into b, so the answer
    # is at a negative offset. A loop that runs 0..MAX_OFFSET_FRAMES finds
    # the previous case and misses this one, which is the whole point of
    # keeping both.
    base = fake_fingerprint(4, 220)
    a = base[6:]
    b = base

    assert compare_fingerprints(a, b) == 0.0
    assert compare_fingerprints(a, b) == compare_fingerprints(b, a)


def test_the_error_rate_divides_by_the_overlap_not_the_whole_list():
    # One flipped bit, but the two lists only overlap by 180 frames, not the
    # 200 and 190 they are long. Dividing by either length gives a different
    # number from the right one.
    base = fake_fingerprint(13, 200)
    b = base[10:]
    b[0] ^= 1

    assert compare_fingerprints(base, b) == pytest.approx(1 / (32 * 180))


def test_a_short_overlap_cannot_win():
    # 90-frame lists whose tail and head agree perfectly at offset 16. That
    # offset leaves an overlap of 74, below the minimum, so it must be
    # refused. Without the minimum it scores 0.0 and wins outright, and two
    # unrelated recordings are declared the same.
    a = fake_fingerprint(5, 90)
    b = fake_fingerprint(6, 90)
    a[16:] = b[:74]

    assert compare_fingerprints(a, b) > 0.3


def test_unrelated_fingerprints_are_far_apart():
    a = fake_fingerprint(7)
    b = fake_fingerprint(8)

    assert 0.4 < compare_fingerprints(a, b) < 0.6


def test_a_fingerprint_too_short_to_compare_returns_none():
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


def test_fingerprints_match_is_false_when_nothing_can_be_compared():
    # The two lists are identical, so the only thing that can produce False
    # is the refusal to compare them at all. Two unrelated short lists would
    # pass this assertion even with the minimum-overlap guard removed, since
    # a rate near 0.5 is over the threshold anyway.
    a = fake_fingerprint(11, 40)

    assert fingerprints_match(a, list(a)) is False
