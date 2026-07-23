"""Compare two collections and sort the second one's tracks into buckets.

Matching is tiered, fastest-and-most-certain first.

We index "mine" by exact file_size and use that as a free pre-filter,
before looking at any tags. Two files with different byte counts can never
be byte-identical, so this cheaply narrows the field to real duplicate
candidates without touching the disk. Only same-size candidates get hashed
(SHA-256), and hashing is the only tier that works when tags are missing
entirely.

Tag+duration fuzzy matching runs only as a fallback, and it's the only tier
that can catch a genuine quality upgrade: the same song in a different
encoding almost always has a different file size, so size/hash structurally
cannot find that pairing. The two tiers are complementary, not competing;
each catches what the other can't.

Fuzzy matches use normalized artist+title and a +/-2 second duration
tolerance. Ambiguous matches (2+ candidates in tolerance) are never
auto-resolved; they go to needs_review for the user to eyeball.

This module is deliberately free of any database access. It reads track
objects and the files they point at, and returns a result. Hashes computed
along the way are cached onto the track objects in place, but persisting
them is the caller's job, which is what keeps this logic unit-testable
against plain in-memory objects.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto

from hashing import compute_file_hash
from models import Track


@dataclass
class Match:
    mine: Track
    theirs: Track


@dataclass
class MatchResult:
    missing: list[Track] = field(default_factory=list)
    upgrade_available: list[Match] = field(default_factory=list)
    already_have: list[Match] = field(default_factory=list)
    needs_review: list[Track] = field(default_factory=list)
    only_in_mine: list[Track] = field(default_factory=list)


class Bucket(Enum):
    """Internal routing key: which list a classified track belongs in.

    only_in_mine has no member here because nothing classifies *into* it;
    it's whatever is left over once every track of theirs is placed.
    """

    MISSING = auto()
    UPGRADE_AVAILABLE = auto()
    ALREADY_HAVE = auto()
    NEEDS_REVIEW = auto()


DURATION_TOLERANCE_SECONDS = 2


def durations_close(a: int, b: int) -> bool:
    # Inclusive: exactly 2 seconds apart still counts as a match. Both
    # sides of that boundary are covered by tests, so tightening this to <
    # will fail loudly rather than quietly shrinking the tolerance.
    return abs(a - b) <= DURATION_TOLERANCE_SECONDS


# Higher number = better quality. Module-level for now; intended to become
# a user-configurable setting later.
#
# FLAC and ALAC tie because both are lossless, so a FLAC/ALAC pairing falls
# through to the bitrate tiebreak rather than being called an upgrade in
# either direction. Note that .m4a files can hold either ALAC (lossless) or
# AAC (lossy) and the extension alone can't tell them apart, so anything
# scanned as "M4A" is currently unranked; disambiguating that needs the
# codec read out of the file itself.
FORMAT_RANK = {
    "FLAC": 3,
    "ALAC": 3,
    "MP3": 1,
    "AAC": 1,
}


def format_rank(fmt: str | None) -> int:
    # Unknown/missing formats rank lowest so they never win an
    # upgrade comparison by accident.
    return FORMAT_RANK.get(fmt.upper(), 0) if fmt else 0


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


def attempt_fuzzy_match(
    theirs_track: Track, tracks_mine: list[Track], consumed: set[int]
):
    """Classify one track of theirs by normalized tags plus duration.

    Returns a (Bucket, payload) pair rather than mutating anything, so the
    decision and its consequences stay separate; route() applies them.
    """
    # Blank-tag guard, and it is load-bearing. Without it, a track of
    # theirs with no artist/title matches every untagged track of mine,
    # because None == None and "" == "" both hold. Whole libraries of
    # untagged rips would collapse into one bogus pairing. Anything blank
    # on either tag is sent straight to missing instead.
    if not normalize(theirs_track.artist) or not normalize(theirs_track.title):
        return (Bucket.MISSING, theirs_track)

    # Scans all of tracks_mine, not just the same-size ones. That's
    # deliberate: this tier exists to find the same recording in a
    # different encoding, which by definition has a different file size.
    # Reusing the size index here would make the tier unable to find the
    # only thing it's for.
    fuzzy_candidates = [
        m
        for m in tracks_mine
        if id(m) not in consumed
        and normalize(m.artist) == normalize(theirs_track.artist)
        and normalize(m.title) == normalize(theirs_track.title)
        and durations_close(m.duration, theirs_track.duration)
    ]
    if len(fuzzy_candidates) == 0:
        return (Bucket.MISSING, theirs_track)
    elif len(fuzzy_candidates) == 1:
        mine_track = fuzzy_candidates[0]

        theirs_rank = format_rank(theirs_track.format)
        mine_rank = format_rank(mine_track.format)

        if theirs_rank > mine_rank:
            return (
                Bucket.UPGRADE_AVAILABLE,
                Match(mine=mine_track, theirs=theirs_track),
            )
        elif theirs_rank < mine_rank:
            return (Bucket.ALREADY_HAVE, Match(mine=mine_track, theirs=theirs_track))
        else:
            # Same format rank, so bitrate breaks the tie. Equal bitrates
            # fall to already_have: without a strict improvement we don't
            # claim an upgrade, since the cost of a wrong "upgrade" is a
            # pointless copy and possibly a deleted original.
            if theirs_track.bit_rate > mine_track.bit_rate:
                return (
                    Bucket.UPGRADE_AVAILABLE,
                    Match(mine=mine_track, theirs=theirs_track),
                )
            else:
                return (
                    Bucket.ALREADY_HAVE,
                    Match(mine=mine_track, theirs=theirs_track),
                )
    else:
        # Two or more candidates within tolerance. Picking one (first,
        # closest duration, best quality) would be a guess that silently
        # decides which of my files gets replaced, so it goes to the user
        # instead. Note this consumes nothing, so every candidate stays
        # available.
        return (Bucket.NEEDS_REVIEW, theirs_track)


def match_collections(
    tracks_mine: list[Track], tracks_theirs: list[Track]
) -> MatchResult:
    result = MatchResult()
    # Tracks of mine already paired with something, held by id() rather
    # than by their database id. Two reasons: an unsaved track has an id of
    # None, so several would collide on the same key, and this module is
    # meant to work on plain in-memory objects that were never persisted at
    # all. Object identity is the only key that's always available and
    # always unique here.
    consumed: set[int] = set()

    mine_by_size: dict[int, list[Track]] = defaultdict(list)
    for track in tracks_mine:
        mine_by_size[track.file_size].append(track)

    for theirs_track in tracks_theirs:
        if theirs_track.file_size in mine_by_size:
            candidates = mine_by_size.get(theirs_track.file_size, [])
            hash_match = False
            # Hash lazily, and only now that a same-size candidate exists.
            # Hashing every track at scan time would read every byte of
            # both collections for nothing.
            if theirs_track.file_hash is None:
                theirs_track.file_hash = compute_file_hash(theirs_track.file_path)
            for mine_track in candidates:
                if id(mine_track) in consumed:
                    continue
                if mine_track.file_hash is None:
                    mine_track.file_hash = compute_file_hash(mine_track.file_path)
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
            # open. Fall through to the fuzzy tier rather than calling it
            # missing outright.
            if not hash_match:
                bucket, payload = attempt_fuzzy_match(
                    theirs_track, tracks_mine, consumed
                )
                route(result, consumed, bucket, payload)
        else:
            bucket, payload = attempt_fuzzy_match(theirs_track, tracks_mine, consumed)
            route(result, consumed, bucket, payload)

    # Whatever was never paired is mine alone: informational, and also the
    # list to hand back to the other collection's owner.
    for mine_track in tracks_mine:
        if id(mine_track) not in consumed:
            result.only_in_mine.append(mine_track)

    return result
