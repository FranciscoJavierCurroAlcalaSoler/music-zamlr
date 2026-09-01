import json
from itertools import count
from pathlib import Path
from typing import NamedTuple

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine as _sa_create_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import database
import main
import scanner
from database import get_session
from main import app
from models import Collection, Track


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


def _refuse_connection():
    raise RuntimeError(
        "A test opened the production database. Pass the test session in "
        "explicitly; don't import `engine` from database.py."
    )


@pytest.fixture(autouse=True)
def no_production_engine(monkeypatch):
    poisoned = _sa_create_engine("sqlite://", creator=_refuse_connection)
    for module in (database, main, scanner):
        monkeypatch.setattr(module, "engine", poisoned, raising=False)


@pytest.fixture
def engine():
    # TestClient dispatches sync endpoints to a worker thread, so the
    # session created here gets used from a different thread than it was
    # made in. check_same_thread=False lifts sqlite3's thread-ownership
    # assertion, and StaticPool makes every checkout reuse the one
    # connection, without which the worker thread would open a second
    # connection and get an empty in-memory database.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def session(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture
def test_collection(session: Session) -> int:
    collection = Collection(
        name="test-collection",
        root_path="/fake/path",
    )
    session.add(collection)
    session.commit()
    session.refresh(collection)
    return collection.id


@pytest.fixture
def make_track():
    def _make_track(**overrides) -> Track:
        defaults = dict(
            file_path="/fake/path.mp3",
            file_name="path.mp3",
            title="Some Title",
            artist="Some Artist",
            album="Some Album",
            track_number=1,
            year=2026,
            format="MP3",
            bit_depth=None,
            bit_rate=320000,
            sample_rate=44100,
            duration=200,
            file_size=5_000_000,
            file_hash=None,
            collection_id=1,
        )
        unknown = set(overrides) - set(defaults)
        if unknown:
            raise TypeError(f"make_track got unknown field(s): {sorted(unknown)}")
        defaults.update(overrides)
        return Track(**defaults)

    return _make_track


@pytest.fixture
def collections(session, tmp_path):
    mine = Collection(name="mine", root_path=str(tmp_path / "mine"))
    theirs = Collection(name="theirs", root_path=str(tmp_path / "theirs"))
    session.add(mine)
    session.add(theirs)
    session.commit()
    return mine, theirs


@pytest.fixture
def destination(tmp_path):
    path = tmp_path / "dest"
    path.mkdir()
    return path


@pytest.fixture
def client(session):
    app.dependency_overrides[get_session] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.clear()


class StreamFrames(NamedTuple):
    """The frames one streaming endpoint sent, in order and split by kind."""

    events: list[str]
    progress: list[dict]
    done: dict | None
    error: dict | None


def parse_sse(body: str) -> StreamFrames:
    """Split an SSE body into frames.

    Frames are separated by a blank line, which is why splitting on "\\n\\n"
    is enough here: json.dumps never emits a bare newline, so a payload can
    not contain the separator.
    """
    events: list[str] = []
    progress: list[dict] = []
    done = None
    error = None
    for block in body.split("\n\n"):
        if not block.strip():
            continue
        event = None
        data = None
        for line in block.splitlines():
            if line.startswith("event: "):
                event = line.removeprefix("event: ")
            elif line.startswith("data: "):
                data = json.loads(line.removeprefix("data: "))
        events.append(event)
        if event == "progress":
            progress.append(data)
        elif event == "done":
            done = data
        elif event == "error":
            error = data
    return StreamFrames(events=events, progress=progress, done=done, error=error)


@pytest.fixture
def event_stream(client, session):
    """Call a streaming endpoint, consume the stream, and return its frames.

    The scan endpoints, /api/diff and both import endpoints no longer answer
    with JSON. They stream Server-Sent Events, and the final frame carries
    what the response body used to, so a test that read response.json() reads
    .done instead.

    The method is a parameter because the scans and imports are POSTs while
    the diff is a GET: the diff's only write is caching hashes onto rows that
    already exist, which is a cache fill rather than a state change.

    Success paths only. A request that fails validation never opens a stream,
    so those tests keep using client.get or client.post and a status code —
    which is what makes them the regression test for "validate first".
    """

    def _event_stream(url, method="POST", **kwargs) -> StreamFrames:
        with client.stream(method, url, **kwargs) as response:
            assert response.status_code == 200, (
                f"{url} answered {response.status_code}, so no stream was opened"
            )
            body = "".join(response.iter_text())
        # Every streaming endpoint does its work on a worker thread holding its
        # own Session, so rows it deleted are gone from the database while this
        # session still has the Python objects in its identity map. Without
        # this, session.get() answers from that map and never looks.
        #
        # Here rather than in each test, because the loud half of that is the
        # smaller half. An "is None" assertion fails and gets fixed; an "is not
        # None" assertion passes whether or not the row survived, and says
        # nothing at all. Three of each exist in test_main.py, and only one
        # kind would ever have told you.
        session.expire_all()
        return parse_sse(body)

    return _event_stream


class Ambiguity(NamedTuple):
    """One or more tracks of theirs that all match the same candidates of mine."""

    theirs: list[Track]
    candidates: list[Track]


@pytest.fixture
def make_ambiguity(session, tmp_path, make_track, collections):
    """Build a track of theirs that lands in needs_review, with its candidates.

    Two things put a track in that bucket and both are easy to break by
    accident, which is why this is a fixture rather than repeated setup:
    two or more of my tracks must fall inside the inclusive ±2s window, and
    every file size must be distinct so the hash tier does not resolve the
    pairing before the fuzzy tier ever runs.

    File names are unique per track. make_track defaults every file_name to
    the same string, which would make any assertion naming a file in an
    error message pass without meaning anything.

    Pass theirs_count=2 for two tracks of theirs sharing one candidate set,
    which is what it takes to double-book a single file of mine.
    """
    mine, theirs = collections
    group_numbers = count(1)

    def _make_ambiguity(
        *, duration=120, theirs_format="MP3", mine_format="MP3", theirs_count=1
    ):
        group = next(group_numbers)
        # Distinct per group as well as within it, so two ambiguities built
        # in one test cannot collide on size and fall into the hash tier.
        sizes = count(group * 10_000_000, 1_000_000)

        def add(collection_id, folder, name, fmt, track_duration):
            track = make_track(
                collection_id=collection_id,
                file_path=str(tmp_path / folder / name),
                file_name=name,
                format=fmt,
                duration=track_duration,
                file_size=next(sizes),
            )
            session.add(track)
            return track

        # duration and duration + 2 straddle theirs at duration + 1, so both
        # are 1s away and both qualify.
        candidates = [
            add(mine.id, "mine", f"mine{group}a.mp3", mine_format, duration),
            add(mine.id, "mine", f"mine{group}b.mp3", mine_format, duration + 2),
        ]
        their_tracks = [
            add(
                theirs.id,
                "theirs",
                f"theirs{group}{chr(ord('a') + n)}.{theirs_format.lower()}",
                theirs_format,
                duration + 1,
            )
            for n in range(theirs_count)
        ]
        session.commit()
        return Ambiguity(theirs=their_tracks, candidates=candidates)

    return _make_ambiguity
