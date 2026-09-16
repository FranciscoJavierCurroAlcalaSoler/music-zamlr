import pytest

from format_order import (
    default_tiers,
    effective_tiers,
    ranks_to_tiers,
    tiers_to_ranks,
    validate_tiers,
)
from matching import FORMAT_RANK, is_lossless, is_lossy


def _flatten(tiers):
    return [name for tier in tiers for name in tier]


def _tier_holding(tiers, name):
    return next(tier for tier in tiers if name in tier)


def test_the_default_order_holds_every_format_once():
    assert sorted(_flatten(default_tiers())) == sorted(FORMAT_RANK)


def test_the_default_order_ranks_every_lossless_format_above_every_lossy_one():
    ranks = tiers_to_ranks(default_tiers())
    lossless_ranks = [ranks[name] for name in FORMAT_RANK if is_lossless(name)]
    lossy_ranks = [ranks[name] for name in FORMAT_RANK if is_lossy(name)]
    assert min(lossless_ranks) > max(lossy_ranks)


def test_the_bottom_tier_ranks_above_an_unknown_format():
    assert min(tiers_to_ranks(default_tiers()).values()) > 0


def test_tiers_and_ranks_round_trip():
    tiers = default_tiers()
    assert ranks_to_tiers(tiers_to_ranks(tiers)) == tiers


def test_the_formats_in_a_tier_keep_one_order():
    # The saved rows arrive in an order of their own, because a database
    # returns rows in whatever order it likes, and the editor shows what comes
    # back. Rows that move between two reads look like a bug to the user.
    default = default_tiers()
    saved_in_another_order = dict(reversed(list(tiers_to_ranks(default).items())))

    assert ranks_to_tiers(saved_in_another_order) == default


def test_a_saved_order_can_rank_a_lossy_format_first():
    ranks = tiers_to_ranks([["MP3"], ["FLAC"]])
    assert ranks["MP3"] > ranks["FLAC"]


def test_the_default_order_is_used_when_nothing_is_saved():
    tiers, placed = effective_tiers({})

    assert tiers == default_tiers()
    assert placed == []


def test_a_format_the_saved_order_does_not_name_joins_the_tier_of_its_kind():
    saved = {
        name: rank
        for name, rank in FORMAT_RANK.items()
        if name not in ("TAK", "MUSEPACK")
    }

    tiers, placed = effective_tiers(saved)

    # Named by a format that shares the kind, not by position: the tiers of a
    # saved order can be in any arrangement, and an index would still pass
    # while the format sat beside the wrong company.
    assert "TAK" in _tier_holding(tiers, "FLAC")
    assert "MUSEPACK" in _tier_holding(tiers, "MP3")
    assert placed == ["TAK", "MUSEPACK"]


def test_a_placed_format_joins_the_lowest_tier_of_its_kind():
    # Two tiers of one kind, which is what makes "lowest" mean anything. With
    # one tier per kind, a search from the top finds the same tier and this
    # rule cannot fail.
    lossless = [name for name in FORMAT_RANK if not is_lossy(name) and name != "TAK"]
    lossy = [name for name in FORMAT_RANK if is_lossy(name)]
    saved = tiers_to_ranks([["FLAC"], [n for n in lossless if n != "FLAC"], lossy])

    tiers, placed = effective_tiers(saved)

    assert tiers[0] == ["FLAC"]
    assert "TAK" in tiers[1]
    assert placed == ["TAK"]


def test_a_kind_with_no_tier_of_its_own_starts_one_at_the_bottom():
    # Only a lossy format is saved, so no tier holds lossless formats at all.
    tiers, placed = effective_tiers({"MP3": 1})

    assert tiers[0][0] == "MP3"
    assert "FLAC" in tiers[-1]
    assert "DSD" in tiers[-1]
    # The other lossy formats join the tier that already holds one.
    assert "AAC" in tiers[0]
    assert sorted(_flatten(tiers)) == sorted(FORMAT_RANK)
    assert "MP3" not in placed


def test_a_saved_row_for_an_unknown_format_is_ignored():
    saved = {**tiers_to_ranks(default_tiers()), "REALAUDIO": 5}

    tiers, placed = effective_tiers(saved)

    assert tiers == default_tiers()
    assert "REALAUDIO" not in _flatten(tiers)
    assert placed == []


def test_an_order_of_only_unknown_formats_falls_back_to_the_default():
    # Every saved row names a format the app no longer has. Without the guard
    # for that case, every known format would count as placed, and the user
    # would be told that the whole order was rebuilt for them.
    tiers, placed = effective_tiers({"REALAUDIO": 5, "SHORTEN": 3})

    assert tiers == default_tiers()
    assert placed == []


def test_validate_tiers_accepts_the_default_order():
    validate_tiers(default_tiers())


def test_validate_tiers_accepts_dsd_beside_lossless_pcm():
    rest = [n for n in FORMAT_RANK if not is_lossy(n) and n not in ("DSD", "FLAC")]
    tiers = [["DSD", "FLAC"], rest, [n for n in FORMAT_RANK if is_lossy(n)]]

    validate_tiers(tiers)


@pytest.mark.parametrize(
    "tiers, error_text",
    [
        ([["MP3", "MP3"], ["FLAC"]], "format appears twice: MP3"),
        ([["MP3"], ["FLAC"], ["REALAUDIO"]], "unknown format: REALAUDIO"),
        ([["MP3"]], "missing formats"),
        ([["FLAC", "MP3"]], "mixed lossy"),
        ([[], ["MP3"], ["FLAC"]], "tier is empty"),
    ],
    ids=["duplicate", "unknown", "missing", "lossy-with-lossless", "empty-tier"],
)
def test_validate_tiers_rejects_a_bad_order(tiers, error_text):
    with pytest.raises(ValueError, match=error_text):
        validate_tiers(tiers)
