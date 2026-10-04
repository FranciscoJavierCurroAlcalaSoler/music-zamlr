"""Compare two collections and sort the second one's tracks into buckets.

Matching is tiered, fastest-and-most-certain first: three tiers, each with
its own pre-filter, and each catching what the others structurally cannot.

**Hash.** We index "mine" by exact file_size and use that as a free
pre-filter, before looking at any tags. Two files with different byte counts
can never be byte-identical, so this cheaply narrows the field to real
duplicate candidates without touching the disk. Only same-size candidates get
hashed (SHA-256). It cannot find a quality upgrade at all: a different
encoding of one recording almost always has a different size. A file that
the filesystem refuses has no hash. Its track goes to the tiers below, so one
unreadable file cannot end a diff.

**Fingerprint.** Chromaprint values, pre-filtered by duration within the same
+/-2 seconds the fuzzy tier uses. This is the tier that reads the audio
itself, so it is the only one that finds the same recording across two
encodings when the tags are missing or wrong — the case the other two are
both blind to. It declines rather than guessing: no fingerprint, no
candidate, or no fpcalc on the machine all send the track down to the tier
below, so the matcher still works exactly as it did before this tier existed.

**Tag + duration fuzzy.** Normalized artist and title within the same
tolerance. It runs last because it is the one that infers identity from
metadata rather than measuring it, but it still resolves pairs the
fingerprint tier cannot — a file too short to fingerprint, or one fpcalc
cannot read.

Ambiguity means the same thing in the last two tiers and is never
auto-resolved: two or more candidates go to needs_review for the user to
eyeball. It is not doubt about the recording. It is doubt about which of my
files a track of theirs corresponds to.

This module is deliberately free of any database access. It reads track
objects and the files they point at, and returns a result. Hashes and
fingerprints computed along the way are cached onto the track objects in
place, but persisting them is the caller's job, which is what keeps this
logic unit-testable against plain in-memory objects.
"""

from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from enums import Bucket
from fingerprinting import (
    FPCALC_ALGORITHM,
    FPCALC_LENGTH_SECONDS,
    SAME_RECORDING_MAX_ERROR_RATE,
    compare_fingerprints,
    compute_fingerprint,
    pack_fingerprint,
    unpack_fingerprint,
)
from hashing import compute_file_hash
from models import Track


@dataclass
class Match:
    mine: Track
    theirs: Track


@dataclass
class RejectedMatch:
    mine: Track
    theirs: Track
    error_rate: float


@dataclass
class ReviewCandidate:
    mine: Track
    would_be: Bucket


@dataclass
class AmbiguousMatch:
    theirs: Track
    candidates: list[ReviewCandidate]


@dataclass
class MatchResult:
    missing: list[Track] = field(default_factory=list)
    upgrade_available: list[Match] = field(default_factory=list)
    already_have: list[Match] = field(default_factory=list)
    needs_review: list[AmbiguousMatch] = field(default_factory=list)
    only_in_mine: list[Track] = field(default_factory=list)
    rejected: list[RejectedMatch] = field(default_factory=list)
    # Paths of the files that a tier tried to read and could not. A track
    # that no tier needed is not on it. Paths, not tracks, because a person
    # needs the path to find the file. The same name as
    # ScanResult.unreadable_files, because the meaning is the same.
    unreadable_files: list[str] = field(default_factory=list)
    # How this result was made, not what it found. False means the audio was
    # never checked and every pairing here rests on tags alone, which the UI
    # warns about. The default exists only because a field without one cannot
    # follow these; match_collections always sets it.
    fingerprints_available: bool = True


@dataclass
class DiffProgress:
    """How far match_collections has got, reported as it goes.

    theirs_count is fixed before any work starts, so unlike a scan this can
    drive a real percentage. Be aware it measures tracks and not time: an
    iteration with no candidate is a dictionary lookup, one with a same-size
    candidate hashes whole files, and one with a same-duration candidate hands
    a file to fpcalc to decode.

    So two counts ride alongside, and they explain different stalls.
    hashed_count is bytes read, which a large FLAC accounts for.
    fingerprinted_count is subprocess calls, which is the slower of the two
    and has no file size on screen to make sense of the wait. Both count work
    actually done rather than candidates examined — a number that climbed for
    a cached value would say the diff is busy while it touches nothing.
    """

    theirs_processed_count: int
    theirs_count: int
    hashed_count: int
    fingerprinted_count: int
    current_path: str | None = None


@dataclass
class FingerprintRun:
    cache: dict[int, list[int] | None] = field(default_factory=dict)
    computed_count: int = 0
    rejections: list[RejectedMatch] = field(default_factory=list)
    # False when the caller found no fpcalc. The tier then declines every
    # track before doing any work, rather than asking fpcalc once per track
    # and being told no each time.
    available: bool = True


DURATION_TOLERANCE_SECONDS = 2


def durations_close(a: int, b: int) -> bool:
    # Inclusive: exactly 2 seconds apart still counts as a match. Both
    # sides of that boundary are covered by tests, so tightening this to <
    # will fail loudly rather than quietly shrinking the tolerance.
    return abs(a - b) <= DURATION_TOLERANCE_SECONDS


# Higher number = better quality. This is the default order, which the matcher
# ranks by when its caller passes none. A caller with a saved order passes that
# instead, as format_ranks.
#
# Every lossless format ties at 3, and every lossy format at 1. A tie between two
# lossless files goes to is_lossless_upgrade, never to bitrate. The scanner
# names ALAC and AAC from the codec of an .m4a file, because the extension
# alone cannot tell them apart.
#
# WAV is uncompressed PCM: audio-identical to a FLAC of the same source, only
# larger. Left out of this table it would rank 0, below MP3, and with the
# delete action a 128 kbps MP3 would then replace a lossless WAV.
FORMAT_RANK = {
    "FLAC": 3,
    "ALAC": 3,
    "WAV": 3,
    "AIFF": 3,
    "TTA": 3,
    "APE": 3,
    "TAK": 3,
    "OPTIMFROG": 3,
    "WAVPACK": 3,
    "WMA LOSSLESS": 3,
    "DSD": 3,
    "MP3": 1,
    "AAC": 1,
    "OPUS": 1,
    "VORBIS": 1,
    "MUSEPACK": 1,
    "WAVPACK HYBRID": 1,
    "WMA": 1,
}

# Whether a format is lossless is a fact about its codec, so it lives here
# and not in FORMAT_RANK. The order is the user's to change, so a rule keyed
# on "rank 3" would change meaning as soon as they reordered the formats.
LOSSLESS_FORMATS = frozenset(
    [
        "FLAC",
        "ALAC",
        "WAV",
        "AIFF",
        "TTA",
        "APE",
        "TAK",
        "OPTIMFROG",
        "WAVPACK",
        "WMA LOSSLESS",
    ]
)

# DSD loses nothing either, but it is 1-bit audio at a sample rate in the
# megahertz range, not PCM, so its bit depth and sample rate measure something
# else. It is not in LOSSLESS_FORMATS: classify_pairing compares a DSD file
# only with another DSD file, never with a PCM file.
DSD_FORMATS = frozenset(["DSD"])


def format_rank(fmt: str | None, format_ranks: Mapping[str, int]) -> int:
    # Unknown/missing formats rank lowest so they never win an
    # upgrade comparison by accident.
    return format_ranks.get(fmt.upper(), 0) if fmt else 0


def is_lossless(fmt: str | None) -> bool:
    return fmt is not None and fmt.upper() in LOSSLESS_FORMATS


def is_dsd(fmt: str | None) -> bool:
    return fmt is not None and fmt.upper() in DSD_FORMATS


def is_lossy(fmt: str | None) -> bool:
    return fmt is not None and not is_lossless(fmt) and not is_dsd(fmt)


def is_lossless_upgrade(mine_track: Track, theirs_track: Track) -> bool:
    """Decide whether their lossless file is better than mine.

    Dominance, not a lexicographic order: theirs must be no worse on bit depth
    and on sample rate, and better on at least one. A pair that is better on
    one value and worse on the other is an upgrade in neither direction, so
    the delete action never removes a file that wins on one of them.
    Comparing (bit_depth, sample_rate) tuples looks the same and is not: the
    first value then decides alone.

    Bitrate takes no part. A lossless bitrate measures how well the audio
    compresses, not how good it is, so an uncompressed WAV or a louder master
    would always win on it.

    A missing value on either side is not an upgrade, and 0 counts as
    missing. mutagen reports an MP4 value that it could not read as 0, and a
    bit depth or sample rate of 0 is never real. Otherwise a value that the
    scanner could not measure loses to any real one, and the delete action
    removes a file that nobody evaluated.
    """
    if not all(
        [
            mine_track.bit_depth,
            mine_track.sample_rate,
            theirs_track.bit_depth,
            theirs_track.sample_rate,
        ]
    ):
        return False
    quality_pairs = [
        (mine_track.bit_depth, theirs_track.bit_depth),
        (mine_track.sample_rate, theirs_track.sample_rate),
    ]
    theirs_no_worse = all(theirs >= mine for mine, theirs in quality_pairs)
    theirs_better = any(theirs > mine for mine, theirs in quality_pairs)
    return theirs_no_worse and theirs_better


def normalize(value: str | None) -> str | None:
    # Returns None for None rather than "", so callers can still tell a
    # missing tag from a present-but-empty one. Both are treated as blank
    # by the guard in attempt_fuzzy_match, but the distinction is worth
    # keeping at this level.
    if value is None:
        return None
    return value.strip().casefold()


def route(result, consumed, bucket, payload):
    """Append a classified track to its bucket, and consume its pair.

    Only ALREADY_HAVE and UPGRADE_AVAILABLE consume a track of mine, and
    that asymmetry is the point. A track of theirs that lands in MISSING or
    NEEDS_REVIEW hasn't been paired with anything, so the tracks of mine it
    was compared against stay available to pair with a later track of
    theirs, and any that never pair end up in only_in_mine.
    """
    if bucket == Bucket.MISSING:
        result.missing.append(payload)
    elif bucket == Bucket.ALREADY_HAVE:
        result.already_have.append(payload)
        consumed.add(id(payload.mine))
    elif bucket == Bucket.UPGRADE_AVAILABLE:
        result.upgrade_available.append(payload)
        consumed.add(id(payload.mine))
    elif bucket == Bucket.NEEDS_REVIEW:
        result.needs_review.append(payload)


def classify_pairing(
    mine_track: Track,
    theirs_track: Track,
    format_ranks: Mapping[str, int] = FORMAT_RANK,
) -> Bucket:
    """Decide which bucket a pairing of mine and theirs falls into.

    Returns only UPGRADE_AVAILABLE or ALREADY_HAVE; the Bucket type is wider
    than this function's range because it is shared with the routing that
    also produces MISSING and NEEDS_REVIEW. It judges quality, never
    identity — whether these two are the same recording was settled by the
    caller, and for a fuzzy match that is a guess inside a ±2s window.

    The format rank decides first. Within one rank, two DSD files or two
    lossless files go to is_lossless_upgrade; a DSD file against any other
    file is not an upgrade; every other pair of equal rank goes to bitrate.

    This is the only definition of "what counts as an upgrade", called both
    for a confirmed single candidate and to label each candidate of an
    ambiguous one. One definition is what stops the review UI promising an
    upgrade the planner would then decline; it is also the single point that
    a configurable ranking has to reach.

    The order arrives as a parameter, never as a module global that a request
    replaces for the length of its diff. A diff runs on a worker thread, so
    two requests with different orders would overwrite each other's ranking
    halfway through. Mapping, not dict, because nothing here may change it:
    the default is the module's own FORMAT_RANK, and a change would outlive
    the diff that made it.
    """
    theirs_rank = format_rank(theirs_track.format, format_ranks)
    mine_rank = format_rank(mine_track.format, format_ranks)

    if theirs_rank > mine_rank:
        return Bucket.UPGRADE_AVAILABLE
    elif theirs_rank < mine_rank:
        return Bucket.ALREADY_HAVE
    else:
        # A DSD file and a PCM file in one rank are an upgrade in neither
        # direction. Their bit depths and sample rates measure different
        # things, and the bitrate rule below would choose the DSD file only
        # because 1-bit audio at megahertz rates has a high bitrate. Two DSD
        # files use dominance: the bit depth is always 1, so the sample rate
        # decides.
        if is_dsd(mine_track.format) or is_dsd(theirs_track.format):
            if is_dsd(mine_track.format) and is_dsd(theirs_track.format):
                if is_lossless_upgrade(mine_track, theirs_track):
                    return Bucket.UPGRADE_AVAILABLE
            return Bucket.ALREADY_HAVE

        # Both branches return. A lossless pair that is not an upgrade must not
        # reach the bitrate code below, where an uncompressed WAV always beats
        # an equal FLAC.
        if is_lossless(mine_track.format) and is_lossless(theirs_track.format):
            if is_lossless_upgrade(mine_track, theirs_track):
                return Bucket.UPGRADE_AVAILABLE
            else:
                return Bucket.ALREADY_HAVE

        # Same format rank and not both lossless, so bitrate breaks the tie.
        # A bitrate of None or 0 on either side claims no upgrade. mutagen
        # reports an MP4 bitrate that it could not read as 0, and that 0
        # would lose to any known bitrate, so the delete action would remove
        # a file that nobody measured. Equal bitrates fall the same way,
        # since without a strict improvement the copy is pointless.
        if not all([theirs_track.bit_rate, mine_track.bit_rate]):
            return Bucket.ALREADY_HAVE
        elif theirs_track.bit_rate > mine_track.bit_rate:
            return Bucket.UPGRADE_AVAILABLE
        else:
            return Bucket.ALREADY_HAVE


def attempt_fuzzy_match(
    theirs_track: Track,
    tracks_mine: list[Track],
    consumed: set[int],
    format_ranks: Mapping[str, int],
):
    """Classify one track of theirs by normalized tags plus duration.

    Returns a (Bucket, payload) pair rather than mutating anything, so the
    decision and its consequences stay separate; route() applies them.

    format_ranks has no default here, and none in the other tier functions.
    The default on classify_pairing serves callers outside this module. Inside
    it, a tier that forgot to pass the order on would rank by the default
    order and answer with it, and every test that runs on the default order
    would still pass. Required, the same mistake is a TypeError on the first
    call.
    """
    # Blank-tag guard, and it is load-bearing. Without it, a track of
    # theirs with no artist/title matches every untagged track of mine,
    # because None == None and "" == "" both hold. Whole libraries of
    # untagged rips would collapse into one bogus pairing. Duration is
    # checked here too: it's nullable when a file won't parse, and
    # durations_close would raise TypeError on None rather than skipping
    # the track. Anything blank or unreadable goes straight to missing.
    if (
        not normalize(theirs_track.artist)
        or not normalize(theirs_track.title)
        or theirs_track.duration is None
    ):
        return (Bucket.MISSING, theirs_track)

    # Scans all of tracks_mine, not just the same-size ones. That's
    # deliberate: this tier exists to find the same recording in a
    # different encoding, which by definition has a different file size.
    # Reusing the size index here would make the tier unable to find the
    # only thing it's for.
    #
    # consumed means "not available to this track", which is wider than its
    # name. _place_track can pass consumed | refused, so a candidate the
    # fingerprint tier compared and refused for this track is skipped too:
    # the tag tier must not re-pair what the audio has already ruled out. The
    # set is only ever read here, never written, which is what makes handing
    # this function a one-off union safe.
    fuzzy_candidates = [
        m
        for m in tracks_mine
        if id(m) not in consumed
        and normalize(m.artist) == normalize(theirs_track.artist)
        and normalize(m.title) == normalize(theirs_track.title)
        and m.duration is not None
        and durations_close(m.duration, theirs_track.duration)
    ]
    if len(fuzzy_candidates) == 0:
        return (Bucket.MISSING, theirs_track)
    elif len(fuzzy_candidates) == 1:
        mine_track = fuzzy_candidates[0]
        return (
            classify_pairing(mine_track, theirs_track, format_ranks=format_ranks),
            Match(mine=mine_track, theirs=theirs_track),
        )
    else:
        # Two or more candidates within tolerance. Picking one (first,
        # closest duration, best quality) would be a guess that silently
        # decides which of my files gets replaced, so it goes to the user
        # instead. Note this consumes nothing, so every candidate stays
        # available.
        return (
            Bucket.NEEDS_REVIEW,
            AmbiguousMatch(
                theirs=theirs_track,
                candidates=[
                    ReviewCandidate(
                        mine=m,
                        would_be=classify_pairing(
                            m, theirs_track, format_ranks=format_ranks
                        ),
                    )
                    for m in fuzzy_candidates
                ],
            ),
        )


def _fingerprint_values(
    track: Track,
    fingerprint_run: FingerprintRun,
) -> list[int] | None:
    """Return one track's fingerprint as integers, computing it if needed.

    Three sources, cheapest first: the local cache, the stored bytes, then
    fpcalc. Stored bytes are trusted only when the producer recorded beside
    them — fpcalc's -length and -algorithm — equals the one in use now. A
    computed fingerprint is packed back onto the track the way the hash tier
    assigns file_hash, and the calling endpoint commits it, so a file is
    decoded once ever, not once per diff.

    None means fpcalc could not read the file, and it is cached like any
    other answer. Without that entry the column stays empty, the next
    candidate finds nothing stored, and one damaged file costs a subprocess
    for every track of theirs that reaches it.

    Keyed by id() rather than track.id, for the reason the consumed set
    above gives: an unsaved track has no database id, so several would share
    the key None.
    """
    if id(track) in fingerprint_run.cache:
        return fingerprint_run.cache[id(track)]
    # A fingerprint from another producer is a cache miss with a reason, not
    # an error. Its bytes are well-formed; they answer a different question,
    # and comparing them against a fresh fingerprint would give a rate that
    # means nothing. So it falls to the branch below exactly as an empty
    # column does — and so does a row with bytes but no producer at all.
    if (
        track.fingerprint is not None
        and track.fingerprint_length == FPCALC_LENGTH_SECONDS
        and track.fingerprint_algorithm == FPCALC_ALGORITHM
    ):
        fingerprint = unpack_fingerprint(track.fingerprint)
    else:
        fingerprint = compute_fingerprint(track.file_path)
        fingerprint_run.computed_count += 1
        if fingerprint is not None:
            track.fingerprint = pack_fingerprint(fingerprint)
            # Both, every time, together with the bytes. New bytes stored
            # without their producer fail the check above on the next diff,
            # which recomputes and stores them producer-less again: every
            # fingerprint decoded on every diff, for good, while any test that
            # reads only the bytes stays green.
            track.fingerprint_length = FPCALC_LENGTH_SECONDS
            track.fingerprint_algorithm = FPCALC_ALGORITHM
    fingerprint_run.cache[id(track)] = fingerprint
    return fingerprint


def attempt_fingerprint_match(
    theirs_track: Track,
    consumed: set[int],
    refused: set[int],
    mine_by_duration: dict[int, list[Track]],
    fingerprint_run: FingerprintRun,
    format_ranks: Mapping[str, int],
) -> tuple[Bucket, Match | AmbiguousMatch | Track] | None:
    """Classify one track of theirs by the sound of it, or decline to.

    The tier the whole phase exists for: it reads the audio, so it finds the
    same recording across two encodings even when the tags are missing or
    wrong, which is exactly where the fuzzy tier below is blind.

    Returns None for "no answer", never a bucket, and the distinction is
    load-bearing. None sends the track down to the fuzzy tier, which still
    resolves pairs this one cannot — a file too short to fingerprint, one
    fpcalc cannot read, or a run on a machine with no fpcalc at all.
    Returning MISSING here would look like an answer and would silently
    switch the tier below off. A rejection is different: every candidate
    compared and every one refused is an answer, and that does return
    MISSING.

    refused is an out-parameter. When the tier declines with some candidates
    refused and some never compared, it holds the refused ones, so the caller
    can keep them from the tier below.
    """
    # None, never MISSING. Without fpcalc the tag tier is the only evidence
    # left, and MISSING would switch it off for every track with a candidate
    # of the right length. And first, before the candidates are built, so
    # nothing reaches _fingerprint_values and computed_count stays at 0.
    # Without that, the progress line counts every failed attempt as a file
    # read, and claims audio was checked while the result warns it was not.
    if fingerprint_run.available is False:
        return None

    if theirs_track.duration is None:
        return None

    # Duration is the pre-filter, and it must not be tags. Tags are the
    # evidence this tier exists to replace, so filtering on them would give
    # it the fuzzy tier's blind spot and it would find nothing new. Duration
    # survives re-encoding, costs no disk read, and the window is the
    # matcher's own tolerance so both tiers accept the same pairs.
    fingerprint_candidates = [
        m
        for d in range(
            theirs_track.duration - DURATION_TOLERANCE_SECONDS,
            theirs_track.duration + DURATION_TOLERANCE_SECONDS + 1,
        )
        for m in mine_by_duration.get(d, [])
        if id(m) not in consumed
    ]
    # Before any fingerprint is computed, deliberately. fpcalc decodes two
    # minutes of audio per call, so a track of theirs with no candidate of a
    # plausible length must cost nothing at all. The hash tier keeps the same
    # discipline: it reads no bytes until a same-size candidate exists.
    if len(fingerprint_candidates) == 0:
        return None

    theirs_fingerprint = _fingerprint_values(theirs_track, fingerprint_run)
    if theirs_fingerprint is None:
        return None

    # Comparable means the comparison produced a number, not merely that a
    # fingerprint was readable. Two conditions, and both are needed.
    #
    # compare_fingerprints expects two real lists, so a candidate fpcalc could
    # not read is dropped first: passing None reaches len() inside it and
    # raises, ending a diff that has already run for minutes over one damaged
    # file.
    #
    # And it declines with None when the shorter fingerprint is under
    # MIN_OVERLAP_FRAMES — about 12 seconds of audio. That is "I cannot tell",
    # not "these differ", and the difference decides whether the tag tier
    # gets its turn. fingerprints_match returns a bool and so collapses the
    # two, which is why this reads the rate itself and applies
    # SAME_RECORDING_MAX_ERROR_RATE below rather than calling that predicate.
    # The rate is kept because computing it is a 33-offset search over every
    # frame, not a lookup worth repeating.
    comparable_candidates = [
        (m, error_rate)
        for m in fingerprint_candidates
        if (mine_fingerprint := _fingerprint_values(m, fingerprint_run)) is not None
        and (error_rate := compare_fingerprints(theirs_fingerprint, mine_fingerprint))
        is not None
    ]
    if len(comparable_candidates) == 0:
        return None

    matching_candidates = [
        m
        for m, error_rate in comparable_candidates
        if error_rate <= SAME_RECORDING_MAX_ERROR_RATE
    ]
    # Every candidate compared, and every one said no. That is an answer, so
    # the tag tier below must not get a second opinion: its evidence is the
    # metadata, and the audio has already contradicted it. A remaster carrying
    # the original's tags and a length inside the tolerance is exactly this
    # case, and only the audio can settle it.
    #
    # MISSING rather than NEEDS_REVIEW because there is nothing to ask. The
    # review dialog's only question is which of my files this supersedes, and
    # the answer is none of them. Importing a different recording as a new
    # file is the correct outcome, and it errs the safe way: a wrong rejection
    # adds a file, where a wrong acceptance deletes one.
    if len(matching_candidates) == 0:
        # A rejection is only a rejection when something was compared. If any
        # candidate could not be — fpcalc could not read it, or it is too
        # short — the refusals rule out only the candidates the audio judged,
        # and the unjudged one may be the real match. So decline, and leave
        # the refused candidates in refused for the tag tier to skip.
        #
        # update() is right on this set and would be wrong on consumed:
        # refused belongs to this one track of theirs, consumed to the whole
        # diff. And no rejection is recorded when declining, because the audio
        # did not judge every candidate and "audio differs" would say it had.
        refused.update(id(m) for m, _ in comparable_candidates)
        if len(comparable_candidates) < len(fingerprint_candidates):
            return None
        # The closest candidate only, never all of them. This list is evidence
        # for one line of UI — "you have a similar file, the audio differs" —
        # and the strongest reason to look is the one worth showing.
        #
        # min with a key rather than min() then a search for it: one pass, and
        # no equality test between two floats to decide which entry won.
        closest_mine, closest_rate = min(comparable_candidates, key=lambda c: c[1])
        fingerprint_run.rejections.append(
            RejectedMatch(
                mine=closest_mine, theirs=theirs_track, error_rate=closest_rate
            )
        )
        return (Bucket.MISSING, theirs_track)
    elif len(matching_candidates) == 1:
        mine_track = matching_candidates[0]
        return (
            classify_pairing(mine_track, theirs_track, format_ranks=format_ranks),
            Match(mine=mine_track, theirs=theirs_track),
        )
    else:
        # Two matches is not doubt about the recording — the fingerprints
        # agree, so it is the same one. It means two of my files hold it, and
        # nothing here can say which to replace. That is the question
        # needs_review already answers for the fuzzy tier, so it reuses the
        # same shape and the same dialog.
        return (
            Bucket.NEEDS_REVIEW,
            AmbiguousMatch(
                theirs=theirs_track,
                candidates=[
                    ReviewCandidate(
                        mine=m,
                        would_be=classify_pairing(
                            m, theirs_track, format_ranks=format_ranks
                        ),
                    )
                    for m in matching_candidates
                ],
            ),
        )


def _place_track(
    theirs_track: Track,
    tracks_mine: list[Track],
    mine_by_duration: dict[int, list[Track]],
    consumed: set[int],
    fingerprint_run: FingerprintRun,
    format_ranks: Mapping[str, int],
) -> tuple[Bucket, Match | AmbiguousMatch | Track]:
    """Run the tiers below the hash tier, best first.

    One function because match_collections reaches this point down two
    different paths — a track of theirs with no same-size candidate, and one
    whose hash did not match. Two copies of the fallthrough would be two
    places to add a tier, and adding it to only one is a silent bug: the
    second path is exactly where a mistagged upgrade lands.

    The return is never None. attempt_fuzzy_match always answers, worst case
    (MISSING, theirs_track), so callers unpack the pair with no further
    check. That is also why the payload here is wider than the fingerprint
    tier's — only the fuzzy tier can hand back a bare Track.
    """
    # Fresh for every track of theirs. On FingerprintRun it would live for the
    # whole diff and carry one track's refusals into the next.
    refused: set[int] = set()
    outcome = attempt_fingerprint_match(
        theirs_track,
        consumed,
        refused,
        mine_by_duration,
        fingerprint_run,
        format_ranks=format_ranks,
    )
    if outcome is None:
        # A union, never consumed.update(refused). Without refused, a decline
        # hands the tag tier a candidate the audio already ruled out, and one
        # whose tags match gets paired — for FLAC over MP3, an upgrade the
        # delete action turns into a deletion. Put into consumed instead, a
        # candidate this track refused is lost to every later track, where it
        # may be the right pairing.
        outcome = attempt_fuzzy_match(
            theirs_track, tracks_mine, consumed | refused, format_ranks=format_ranks
        )
    return outcome


def match_collections(
    tracks_mine: list[Track],
    tracks_theirs: list[Track],
    on_progress: Callable[[DiffProgress], None] | None = None,
    fingerprints_available: bool = True,
    format_ranks: Mapping[str, int] = FORMAT_RANK,
) -> MatchResult:
    # Told, never looked up here: the caller asks PATH once per diff. A matcher
    # that looked for itself would pass or fail its tests according to what
    # the machine has installed. The planner receives path_exists for the same
    # reason. The format order arrives the same way, and the endpoint reads it
    # from the database once per diff.
    result = MatchResult(fingerprints_available=fingerprints_available)
    # Tracks of mine already paired with something, held by id() rather
    # than by their database id. Two reasons: an unsaved track has an id of
    # None, so several would collide on the same key, and this module is
    # meant to work on plain in-memory objects that were never persisted at
    # all. Object identity is the only key that's always available and
    # always unique here.
    consumed: set[int] = set()
    # Tracks whose file the hash tier could not read in this diff, by id()
    # for the reason above. file_hash = None means both "not tried" and
    # "could not read", and this set keeps the two apart. Without it, one
    # unreadable file of mine is opened again for every track of theirs with
    # its size.
    hash_failures: set[int] = set()
    # Unpacked fingerprints, for the length of this diff only. The database
    # column already stops fpcalc running twice across runs, but it holds
    # bytes and the comparison needs integers, so without this the same 3792
    # bytes are decoded again for every candidate a track is measured
    # against. It also holds None, which the column cannot: an empty column
    # means both "no fingerprint" and "not tried yet", and only this tells
    # the two apart within a run.
    fingerprint_run = FingerprintRun(available=fingerprints_available)
    hashed_count = 0
    theirs_processed_count = 0

    def report(current_path: str | None = None) -> None:
        if on_progress is not None:
            # A new object per call. The value handed to a callback is a
            # statement about one moment, and a caller that keeps what it
            # receives must not watch it change underneath.
            on_progress(
                DiffProgress(
                    theirs_processed_count=theirs_processed_count,
                    theirs_count=len(tracks_theirs),
                    hashed_count=hashed_count,
                    fingerprinted_count=fingerprint_run.computed_count,
                    current_path=current_path,
                )
            )

    def hash_or_none(track: Track) -> str | None:
        """Return a track's hash, and read its file at most once per diff.

        One helper for both sides, because the track of theirs and each
        candidate of mine need the same rules, and two copies can become
        different.

        hashed_count increases only when a file was read. A stored hash costs
        nothing, and a failed read reads nothing. A count that increased for
        either would show a busy diff that reads no bytes.
        """
        nonlocal hashed_count
        if track.file_hash is not None:
            return track.file_hash
        if id(track) in hash_failures:
            return None
        result = compute_file_hash(track.file_path)
        if result is None:
            hash_failures.add(id(track))
            return None
        track.file_hash = result
        hashed_count += 1
        return result

    # Two indexes over the same pass. Size feeds the hash tier, duration
    # feeds the fingerprint tier, and neither can do the other's job: two
    # encodings of one recording differ in size, and two unrelated tracks
    # share a duration constantly.
    mine_by_size: dict[int, list[Track]] = defaultdict(list)
    mine_by_duration: dict[int, list[Track]] = defaultdict(list)
    for track in tracks_mine:
        mine_by_size[track.file_size].append(track)
        # A track with no readable duration is left out rather than filed
        # under None, which would make one bucket that every unreadable file
        # shares and that no track of theirs can ever look up.
        if track.duration is not None:
            mine_by_duration[track.duration].append(track)

    for theirs_track in tracks_theirs:
        # Reported before the work, not after it. The expensive part of an
        # iteration is the hashing below, and a report at the end would leave
        # the caller naming a file that finished while a 300 MB FLAC is being
        # read. Announcing the file first makes current_path mean "working on
        # this", which is what a progress display is for.
        report(theirs_track.file_path)
        if theirs_track.file_size in mine_by_size:
            candidates = mine_by_size.get(theirs_track.file_size, [])
            hash_match = False
            # Hash lazily, and only now that a same-size candidate exists.
            # Hashing every track at scan time would read every byte of
            # both collections for nothing.
            hash_result = hash_or_none(theirs_track)
            # The only guard against None == None. Without it, two unreadable
            # files of one size compare equal, and the diff calls them
            # byte-identical. The candidates need no guard of their own: here
            # theirs has a hash, so a candidate without one compares unequal.
            # The skip also saves the reads of candidates for a comparison
            # that cannot succeed.
            if hash_result is not None:
                for mine_track in candidates:
                    if id(mine_track) in consumed:
                        continue
                    hash_or_none(mine_track)
                    if theirs_track.file_hash == mine_track.file_hash:
                        hash_match = True
                        result.already_have.append(
                            Match(mine=mine_track, theirs=theirs_track)
                        )
                        consumed.add(id(mine_track))
                        # First byte-identical copy wins; the rest of the
                        # same-size candidates can't be a better answer.
                        break
            # Same size but different content, so this pairing is still
            # open. Fall through to the tiers below rather than calling it
            # missing outright. This is the path a mistagged upgrade takes
            # when it happens to share a size with something of mine, so it
            # needs the fingerprint tier as much as the branch below does.
            if not hash_match:
                bucket, payload = _place_track(
                    theirs_track,
                    tracks_mine,
                    mine_by_duration,
                    consumed,
                    fingerprint_run,
                    format_ranks=format_ranks,
                )
                route(result, consumed, bucket, payload)
        else:
            bucket, payload = _place_track(
                theirs_track,
                tracks_mine,
                mine_by_duration,
                consumed,
                fingerprint_run,
                format_ranks=format_ranks,
            )
            route(result, consumed, bucket, payload)
        theirs_processed_count += 1

    # The closing report, and the only one with no file in progress. It exists
    # so the caller ends on processed == total rather than one short. The loop
    # below moves none of these numbers and does no I/O, so it needs none.
    report()

    # Whatever was never paired is mine alone: informational, and also the
    # list to hand back to the other collection's owner.
    for mine_track in tracks_mine:
        if id(mine_track) not in consumed:
            result.only_in_mine.append(mine_track)

    # One pass at the end, because a fingerprint failure occurs in
    # _fingerprint_values, which does not know the result. Theirs come first,
    # so the list has the same order on every run, and a track that failed in
    # both tiers appears once. Examine the cache key with "in" before the
    # value: .get() also returns None for a track that no tier tried, and
    # every track without a candidate then goes on the list.
    for track in [*tracks_theirs, *tracks_mine]:
        if id(track) in hash_failures or (
            id(track) in fingerprint_run.cache
            and fingerprint_run.cache[id(track)] is None
        ):
            result.unreadable_files.append(track.file_path)

    # Copied rather than aliased. fingerprint_run dies with this call today, so
    # sharing the list is harmless — but a result that can be mutated through
    # an object the caller never saw is a surprise waiting for whoever gives
    # the run a longer life.
    result.rejected = list(fingerprint_run.rejections)

    return result
