"""Read a Chromaprint fingerprint from an audio file, and compare two of them.

A fingerprint is a list of 32-bit integers, one per frame, where a frame
covers about 0.1238 seconds of decoded audio. Two encodings of the same
recording produce fingerprints that are similar rather than equal: most bits
of each integer agree, and the two lists can begin at different points in the
music because one file carries silence or a different track split.

So the comparison cannot be equality. It is a bit error rate — the fraction
of compared bits that disagree — taken at whichever offset fits the two lists
together best. Measured against real files, the same recording scores between
0.00 and 0.055 and two different recordings score about 0.47.

This module only ever compares two fingerprints against each other. It never
identifies one. Identification is what an AcoustID lookup does, and it would
mean sending a fingerprint per track to a third party, which is the thing the
local-first design exists to avoid.

Only compute_fingerprint touches the disk, and it does so by starting fpcalc
rather than by reading the file itself. Everything below it is arithmetic
over lists of integers, which is what keeps the comparison testable against
values typed into a test rather than against audio.

Nothing here reaches the database, and nothing here imports matching.py:
matching.py imports this module, so the reverse would be an import cycle.
"""

import logging
import shutil
import struct
import subprocess

FRAME_SECONDS = 0.1238

# The width of the offset search, and the reason this is tractable at all.
# Only pairs already within the matcher's duration tolerance of +/-2 seconds
# ever reach this module, so one recording cannot begin more than
# 2 / FRAME_SECONDS ~= 16 frames before the other. That bound turns an
# alignment problem into a fixed 33-offset loop.
#
# This comment is where the coupling lives, because code cannot carry it:
# DURATION_TOLERANCE_SECONDS belongs to matching.py, which imports this
# module, so importing the tolerance back would be a cycle. Widen the
# tolerance there without widening this, and the tier quietly stops aligning
# pairs that the fuzzy tier still accepts.
MAX_OFFSET_FRAMES = 16

# The fewest frames an offset must line up before its score is allowed to
# count. A short overlap makes accidental agreement decisive: two unrelated
# tracks can share a handful of frames by luck, and a stretch that agrees
# perfectly scores 0.0 and wins the whole search.
#
# With MAX_OFFSET_FRAMES at 16, the overlap only drops under 80 for
# fingerprints shorter than 96 frames, about 12 seconds of audio. So this
# guards short files specifically.
MIN_OVERLAP_FRAMES = 80

# At or under this rate, two fingerprints are the same recording. Not a
# delicate number: the measured gap runs from 0.055 for a re-encode up to
# 0.47 for an unrelated track, so anything from roughly 0.10 to 0.25 divides
# them. Phase 6's configurable ranking is the one caller that should ever
# need to move it.
SAME_RECORDING_MAX_ERROR_RATE = 0.15

FPCALC_LENGTH_SECONDS = 120
FPCALC_TIMEOUT_SECONDS = 60

# Passed to fpcalc explicitly, never inherited, for the reason -length is: a
# fingerprint is stored and compared later against one another run produced,
# and two algorithms give values that cannot be compared at all. 2 is fpcalc
# 1.6.1's own default — omitting the flag and passing it give byte-identical
# output — so this changes nothing today. It stops a future default from
# moving under the values already in the database.
#
# Recorded on the row beside the length, and those two are the whole
# producer. The fpcalc version is deliberately not recorded: a patch release
# does not change what a fingerprint means, and recording it would invalidate
# the entire column every time the binary was updated, for nothing.
FPCALC_ALGORITHM = 2


def _error_rate_at_offset(a: list[int], b: list[int], offset: int) -> float | None:
    """Score one alignment of the two fingerprints, or refuse to score it.

    A positive offset means that `a` begins later than `b`, so the front of
    `a` and the tail of `b` hang over the ends and are discarded. A negative
    offset is the mirror of that. Returns None when the frames that remain
    are too few to trust, which the caller must not read as a bad score.
    """
    if offset >= 0:
        a_slice = a[offset:]
        b_slice = b[: len(b) - offset]
    else:
        a_slice = a[: len(a) + offset]
        b_slice = b[-offset:]

    frame_count = min(len(a_slice), len(b_slice))

    if frame_count < MIN_OVERLAP_FRAMES:
        return None

    a_slice = a_slice[:frame_count]
    b_slice = b_slice[:frame_count]

    different_bits = 0
    for n in range(frame_count):
        # The mask is a no-op against fpcalc 1.6.1, which prints unsigned
        # values. It stays because bit_count() on a negative number counts
        # the bits of its absolute value instead of raising, so a later
        # fpcalc that printed signed values would not fail here — it would
        # return a plausible wrong rate for every pair, forever.
        different_bits += ((a_slice[n] ^ b_slice[n]) & 0xFFFFFFFF).bit_count()

    return different_bits / (32 * frame_count)


def compare_fingerprints(a: list[int], b: list[int]) -> float | None:
    """Return the best error rate across every offset, or None if there is none.

    None means "no answer", never "completely different". A rate of 1.0 is a
    legal score that means every compared bit disagreed, so collapsing the two
    into one number would leave the caller unable to tell a rejection from a
    refusal. The tier above needs them apart: a fingerprint that says no must
    stop a pairing, while a fingerprint that cannot answer must let the tag
    matcher try instead.

    None comes back exactly when the shorter fingerprint holds fewer than
    MIN_OVERLAP_FRAMES frames, because offset 0 always overlaps by the length
    of the shorter list. It is a length check, not a failed search.
    """
    lowest_error_rate: float | None = None

    for i in range(-MAX_OFFSET_FRAMES, MAX_OFFSET_FRAMES + 1):
        current_error_rate = _error_rate_at_offset(a, b, i)
        if current_error_rate is None:
            continue
        elif lowest_error_rate is None:
            lowest_error_rate = current_error_rate
        elif current_error_rate < lowest_error_rate:
            lowest_error_rate = current_error_rate

    return lowest_error_rate


def fingerprints_match(a: list[int], b: list[int]) -> bool:
    error_rate = compare_fingerprints(a, b)
    if error_rate is None or error_rate > SAME_RECORDING_MAX_ERROR_RATE:
        return False
    return True


def _find_fpcalc() -> str | None:
    return shutil.which("fpcalc")


def fpcalc_available() -> bool:
    """Say whether fpcalc is on PATH, without running it.

    Through _find_fpcalc rather than a second shutil.which, so the stub that
    replaces the lookup in the tests governs this answer too. A second lookup
    would ignore the stub, and a test would pass or fail by what the machine
    has installed.

    It finds the file and nothing more. An fpcalc that is present but broken
    still answers True here, and compute_fingerprint then fails file by file,
    as it always has.
    """
    return _find_fpcalc() is not None


def compute_fingerprint(file_path: str) -> list[int] | None:
    fpcalc_path = _find_fpcalc()
    if fpcalc_path is None:
        logging.warning("fpcalc binary not found in PATH")
        return None

    try:
        result = subprocess.run(
            [
                fpcalc_path,
                "-raw",
                "-length",
                str(FPCALC_LENGTH_SECONDS),
                "-algorithm",
                str(FPCALC_ALGORITHM),
                file_path,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=FPCALC_TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            # fpcalc's own stderr says why, for example that it could not open
            # the file. No test reads that text: part of it comes from the
            # operating system, in the user's language.
            logging.warning(
                "fpcalc failed with return code %d for %s: %s",
                result.returncode,
                file_path,
                result.stderr.strip(),
            )
            return None
    # TimeoutExpired and OSError only. CalledProcessError cannot reach here,
    # because subprocess.run raises it only when called with check=True, and
    # the return code is examined above instead.
    except (subprocess.TimeoutExpired, OSError) as e:
        logging.warning("fpcalc failed on %s: %s", file_path, e)
        return None

    # Read by prefix rather than by line number. fpcalc writes DURATION and
    # FINGERPRINT on separate lines, and nothing promises an order.
    for line in result.stdout.splitlines():
        if line.startswith("FINGERPRINT="):
            values = line.removeprefix("FINGERPRINT=")
            try:
                return [int(value) for value in values.split(",")]
            except ValueError:
                # Close to impossible, since fpcalc exiting 0 means it wrote a
                # fingerprint. It is caught anyway because this is the last
                # path on which one unreadable file could still end a whole
                # diff, which is the rule every other branch here obeys.
                logging.warning(
                    "fpcalc wrote a non-numeric fingerprint for %s", file_path
                )
                return None

    logging.warning("fpcalc output did not contain a fingerprint for %s", file_path)
    return None


def pack_fingerprint(fingerprint: list[int]) -> bytes:
    """Turn a fingerprint into the bytes stored in Track.fingerprint.

    `<I` is the whole decision, and both halves of it are deliberate. `I` is
    an unsigned 32-bit value, which is what a frame is. `<` fixes the byte
    order as little-endian rather than letting the machine pick, and without
    it `struct` also chooses its own width for `I`, which is not guaranteed
    to be four bytes.

    Neither is a portability nicety. The bytes outlive the process that
    wrote them: a row written last month is unpacked by whatever version of
    this module runs next, so the layout is a promise between two runs and
    not an internal detail. That is also why one test asserts the literal
    bytes — pack and unpack agree with each other under any byte order, so a
    round trip cannot notice the format changing underneath it.
    """
    return b"".join(struct.pack("<I", value) for value in fingerprint)


def unpack_fingerprint(data: bytes) -> list[int]:
    """Read back what pack_fingerprint wrote.

    A length that is not a multiple of four raises struct.error rather than
    returning a short fingerprint, because a truncated blob is a corrupt row
    and a silently shortened list would compare as a genuine, poor match.
    """
    return [struct.unpack("<I", data[i : i + 4])[0] for i in range(0, len(data), 4)]
