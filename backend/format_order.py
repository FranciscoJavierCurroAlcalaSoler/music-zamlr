"""Build, complete and check a format order, with no storage of its own.

A **tier** is a list of format names that tie. An **order** is a list of
tiers, best first. A **rank** is the number the matcher compares, which
classify_pairing takes as a parameter.

Two sources meet here, and they answer different questions. FORMAT_RANK is
the set of formats the scanner can produce, plus the order to use when the
user has chosen none: it must live in code, because a new install has no
saved rows and a format added by an update has none either. The saved rows
hold only the user's choice, so they can be incomplete, and they can name a
format that no longer exists.

No database and no FastAPI here, as in the other logic modules: these
functions read lists of strings, so their tests need neither a session nor a
request.
"""

from collections.abc import Mapping

from matching import FORMAT_RANK, is_lossy


def default_tiers() -> list[list[str]]:
    # Derived from FORMAT_RANK, never written out a second time by hand. A
    # format added there would be missing from a hand-written default, so the
    # editor would not show it and nobody could rank it.
    by_rank = {}
    for name, rank in FORMAT_RANK.items():
        by_rank.setdefault(rank, []).append(name)
    return [by_rank[rank] for rank in sorted(by_rank, reverse=True)]


def tiers_to_ranks(tiers: list[list[str]]) -> dict[str, int]:
    # The bottom tier gets 1, never 0. format_rank answers 0 for a format it
    # does not know, so a bottom tier of 0 would tie every real format with an
    # unreadable one. The numbers carry no other meaning: the matcher only
    # compares them with each other.
    return {
        name: len(tiers) - index for index, tier in enumerate(tiers) for name in tier
    }


def ranks_to_tiers(ranks: Mapping[str, int]) -> list[list[str]]:
    # Walks FORMAT_RANK rather than the saved rows, so the formats inside a
    # tier always come out in the same order. The editor shows these rows, and
    # rows that move between two reads look like a bug to the user. A saved
    # name that FORMAT_RANK does not know is left out here as well.
    by_rank = {}
    for name in FORMAT_RANK:
        if name in ranks:
            by_rank.setdefault(ranks[name], []).append(name)
    return [by_rank[rank] for rank in sorted(by_rank, reverse=True)]


def effective_tiers(
    saved_ranks: Mapping[str, int],
) -> tuple[list[list[str]], list[str]]:
    """Return the order to use, and the formats this function placed itself.

    The saved rows are treated as a preference, not as the truth: a row for a
    format the app no longer has is dropped, and a format the rows never name
    is placed. The placed names come back to the caller because the user has
    to be told which formats were put in for them; a format that appeared in
    the editor after an update would otherwise have no explanation.

    A format is placed in the lowest tier of its own kind, never the top one:
    a format nobody ranked must not outrank one the user ranked on purpose.
    Lossy against everything else is the whole of "kind" here, so a new
    lossless format may join a tier that holds DSD.
    """
    known_saved_ranks = {
        name: rank for name, rank in saved_ranks.items() if name in FORMAT_RANK
    }
    if not known_saved_ranks:
        return default_tiers(), []

    tiers = ranks_to_tiers(known_saved_ranks)
    placed = []
    for name in FORMAT_RANK:
        if name in known_saved_ranks:
            continue
        kind = is_lossy(name)
        destination = None
        # From the bottom up, and the first name decides a tier's kind: a
        # stored tier holds one kind only, because validate_tiers refused to
        # store any other. A kind with no tier at all starts one at the
        # bottom, which is where the first format of a kind the user never
        # ranked belongs.
        for index in range(len(tiers) - 1, -1, -1):
            if is_lossy(tiers[index][0]) == kind:
                destination = index
                break
        if destination is None:
            tiers.append([name])
        else:
            tiers[destination].append(name)
        placed.append(name)
    return tiers, placed


def validate_tiers(tiers: list[list[str]]) -> None:
    """Raise ValueError unless the tiers are an order the server can store.

    A saved order replaces the whole order, so a missing format is an error
    here rather than something to fill in: effective_tiers completes, this
    function judges. Every message names the formats it objects to, because
    the endpoint hands the message to the user, and "invalid order" does not
    say which chip to move.

    The rules are facts about formats, not about HTTP, which is why they live
    beside the formats and not in the endpoint.
    """
    seen = set()
    for tier in tiers:
        if not tier:
            raise ValueError("tier is empty")
        tier_lossiness = is_lossy(tier[0])
        for name in tier:
            if name not in FORMAT_RANK:
                raise ValueError(f"unknown format: {name}")
            if name in seen:
                raise ValueError(f"format appears twice: {name}")
            seen.add(name)
            if is_lossy(name) != tier_lossiness:
                raise ValueError(
                    f"mixed lossy and non-lossy formats: {', '.join(tier)}"
                )

    missing = [name for name in FORMAT_RANK if name not in seen]
    if missing:
        raise ValueError(f"missing formats: {', '.join(missing)}")
