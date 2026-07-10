from collections import defaultdict
from dataclasses import dataclass, field

from models import Track
from hashing import compute_file_hash
from enum import Enum, auto

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
    MISSING = auto()
    UPGRADE_AVAILABLE = auto()
    ALREADY_HAVE = auto()
    NEEDS_REVIEW = auto()


DURATION_TOLERANCE_SECONDS = 2

def durations_close(a: int, b: int) -> bool:
    return abs(a - b) <= DURATION_TOLERANCE_SECONDS


# Higher number = better quality. Module-level for now; becomes a
# user-configurable setting in Phase 6 (spec §5 quality ranking).
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
    if value is None:
        return None
    return value.strip().casefold()


def route(result, consumed, bucket, payload):
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


def attempt_fuzzy_match(theirs_track: Track, tracks_mine: list[Track], consumed: set[int]):

    if not normalize(theirs_track.artist) or not normalize(theirs_track.title):
        return (Bucket.MISSING, theirs_track)

    fuzzy_candidates = [
        m for m in tracks_mine
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
            return (Bucket.UPGRADE_AVAILABLE, Match(mine=mine_track, theirs=theirs_track))
        elif theirs_rank < mine_rank:
            return (Bucket.ALREADY_HAVE, Match(mine=mine_track, theirs=theirs_track))
        else:
            if theirs_track.bit_rate > mine_track.bit_rate:
                return (Bucket.UPGRADE_AVAILABLE, Match(mine=mine_track, theirs=theirs_track))
            else:
                return (Bucket.ALREADY_HAVE, Match(mine=mine_track, theirs=theirs_track))
    else:
        return (Bucket.NEEDS_REVIEW, theirs_track)



def match_collections(tracks_mine: list[Track], tracks_theirs: list[Track]) -> MatchResult:
    result = MatchResult()
    consumed: set[int] = set()

    mine_by_size: dict[int, list[Track]] = defaultdict(list)
    for track in tracks_mine:
        mine_by_size[track.file_size].append(track)

    for theirs_track in tracks_theirs:
        if theirs_track.file_size in mine_by_size:
            candidates = mine_by_size.get(theirs_track.file_size, [])
            hash_match = False
            if theirs_track.file_hash is None:
                theirs_track.file_hash = compute_file_hash(theirs_track.file_path)
            for mine_track in candidates:
                if id(mine_track) in consumed:
                    continue
                if mine_track.file_hash is None:
                    mine_track.file_hash = compute_file_hash(mine_track.file_path)
                if theirs_track.file_hash == mine_track.file_hash:
                    hash_match = True
                    result.already_have.append(Match(mine=mine_track, theirs=theirs_track))
                    consumed.add(id(mine_track))
                    break
            if not hash_match:
                bucket, payload = attempt_fuzzy_match(theirs_track, tracks_mine, consumed)
                route(result, consumed, bucket, payload)
        else:
            bucket, payload = attempt_fuzzy_match(theirs_track, tracks_mine, consumed)
            route(result, consumed, bucket, payload)

    for mine_track in tracks_mine:
        if id(mine_track) not in consumed:
            result.only_in_mine.append(mine_track) 

    return result
