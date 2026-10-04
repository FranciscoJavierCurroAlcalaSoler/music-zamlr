"""The names the frontend reads, pinned from this side.

`frontend/src/types.ts` is a hand-written claim about what FastAPI sends,
and TypeScript cannot check it: `tsc` believes a field the server never
sends, and the screen renders `undefined`.

These tests hold the other half of the contract. They compare the whole key
set of a response with a literal, so a key that is dropped fails here before
the UI reads nothing, and a key that is added fails too — a new field is a
decision for `types.ts`, and a test that stays green while the wire grows
teaches nobody anything.

The expected names are written out rather than taken from `schemas.py`. A
test that asks the schema what the schema says cannot fail.

Not covered: the type of any value, and the endpoints the window does not
read on startup or on its main screen — both imports, the scan result and
the two progress frames. Only a test driving a real browser reaches
those.
"""

import pytest


def test_health_keys(client):
    body = client.get("/api/health").json()

    assert set(body) == {"status"}


# Requested for its effect, not its value: the fixture inserts a row, and
# the endpoint answers [] without one, which fails on the subscript before
# it reaches the assertion and so fails the same way whatever the keys are.
@pytest.mark.usefixtures("test_collection")
def test_collection_keys(client):
    body = client.get("/api/collections").json()

    # Narrower than the table on purpose: CollectionRead exposes four fields
    # and the model has more. The test states the four rather than whatever
    # the schema happens to carry.
    assert set(body[0]) == {"id", "name", "root_path", "last_scanned_at"}


def test_format_order_keys(client):
    # No fixture: the endpoint answers with the default order when nothing
    # has been saved, which is what a first run gets.
    body = client.get("/api/settings/format-order").json()

    assert set(body) == {
        "tiers",
        "default_tiers",
        "placed",
        "lossy_formats",
        "updated_at",
    }


def test_diff_keys(session, make_track, collections, event_stream):
    # The richest body, feeding the screen the user works in, with fields
    # nested two levels deep, where a rename is easiest to miss. The done
    # frame is asserted rather than the status code: a stream answers 200
    # even when its body is an error frame.
    mine, theirs = collections
    session.add(make_track(file_path="/theirs/song.mp3", collection_id=theirs.id))
    session.commit()

    body = event_stream(f"/api/diff?mine={mine.id}&theirs={theirs.id}", "GET").done

    assert set(body) == {"match_results", "match_counts"}
    assert set(body["match_results"]) == {
        "missing",
        "upgrade_available",
        "already_have",
        "needs_review",
        "only_in_mine",
        "rejected",
        "fingerprints_available",
        "unreadable_files",
    }
    assert set(body["match_counts"]) == {
        "missing",
        "upgrade_available",
        "already_have",
        "needs_review",
        "only_in_mine",
    }
