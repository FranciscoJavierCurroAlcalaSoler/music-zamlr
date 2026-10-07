import json
import os
import random
import struct
import subprocess
from itertools import count
from pathlib import Path
from typing import NamedTuple

import pytest
from fastapi.testclient import TestClient
from mutagen.apev2 import APEv2
from mutagen.dsdiff import DSDIFF
from mutagen.dsf import DSF
from mutagen.id3 import TALB, TDRC, TIT2, TPE1, TRCK
from sqlalchemy import create_engine as _sa_create_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import database
import main
import scanner
from database import get_session
from main import app
from models import Collection, Track
from serve import PORT_LINE_PREFIX


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


# The stream values in every header-only file. No two are equal, and none is
# the 44.1 kHz and 16 bits of the fixture files, so a field read from the
# wrong bits gives a wrong value instead of a lucky right one.
_SAMPLE_RATE = 96000
_BIT_DEPTH = 24
_CHANNELS = 2
_SECONDS = 3


def _tak_header() -> bytes:
    # The STREAM_INFO fields, packed from the lowest bit up, because TAK
    # reads each byte from its lowest bit: 6 bits codec, 4 profile, 4 frame
    # size, 35 sample count, 3 data type, 18 sample rate above 6000, 5 bit
    # depth above 8, 4 channels above 1, 1 extension flag. The fields that
    # stay 0 are fields the scanner does not read.
    fields = (
        (_SAMPLE_RATE * _SECONDS) << 14
        | (_SAMPLE_RATE - 6000) << 52
        | (_BIT_DEPTH - 8) << 70
        | (_CHANNELS - 1) << 75
    )
    # The 80 bits fill 10 bytes. 3 zero bytes take the place of the CRC,
    # which mutagen does not check but counts in the block size.
    stream_info = fields.to_bytes(10, "little") + bytes(3)
    # Each block starts with its type in one byte (1 is STREAM_INFO) and its
    # size in 3 little-endian bytes. A block of type 0 (END) stops the reader.
    stream_info_block = bytes([1]) + len(stream_info).to_bytes(3, "little")
    return b"tBaK" + stream_info_block + stream_info + bytes(4)


def _optimfrog_header() -> bytes:
    # After the "OFR " magic: the size of the header data, which must be 15
    # or more for OptimFROG 4.5 and later; the sample count over all
    # channels, as 32 low bits and 16 high bits; the sample type (4 is
    # 24-bit); the channels less 1; the sample rate; the encoder id.
    fields = struct.pack(
        "<IHBBIH",
        _SAMPLE_RATE * _SECONDS * _CHANNELS,
        0,
        4,
        _CHANNELS - 1,
        _SAMPLE_RATE,
        0,
    )
    # mutagen reads exactly 76 bytes and refuses a shorter header.
    return (b"OFR " + struct.pack("<I", 15) + fields).ljust(76, b"\0")


@pytest.fixture
def make_header_only_file(tmp_path):
    """Write a TAK or OptimFROG file with a stream header and APEv2 tags.

    ffmpeg can encode neither format, so the tests build these files. A file
    holds no audio, which is enough for read_track: it reads only the header
    and the tags. It is not enough for fpcalc, so do not use one in a test
    that needs the sound.

    The extension of the name chooses the header. The tags follow the fixture
    files, with the extension in the title, and APEv2 writes them under
    "Track" and "Year".
    """
    headers = {".tak": _tak_header, ".ofr": _optimfrog_header}

    def _make_header_only_file(name: str) -> Path:
        path = tmp_path / name
        extension = path.suffix.lower()
        path.write_bytes(headers[extension]())
        tags = APEv2()
        tags["Title"] = f"Test Track {extension[1:].upper()}"
        tags["Artist"] = "Music Zamlr Fixtures"
        tags["Album"] = "Synthetic Test Album"
        tags["Year"] = "2026"
        tags["Track"] = "3/10"
        # save appends the tag block to the end of the file, where APEv2
        # readers look for it.
        tags.save(path)
        return path

    return _make_header_only_file


# The stream values in every DSD file. DSD64 is the most common DSD rate, and
# 2 seconds keeps the duration apart from the 1 second of the fixture files.
_DSD_SAMPLE_RATE = 2822400
_DSD_CHANNELS = 2
_DSD_SECONDS = 2
# The byte pattern that DSD uses for silence.
_DSD_SILENCE = b"\x69"


def _dsf_bytes() -> bytes:
    # DSF is little-endian, with 8-byte sizes. The sample count is for each
    # channel, and each channel's data fills whole blocks of 4096 bytes.
    # -(-a // b) is a division that rounds up.
    samples = _DSD_SAMPLE_RATE * _DSD_SECONDS
    blocks = -(-samples // 8 // 4096)
    data = _DSD_SILENCE * (blocks * 4096 * _DSD_CHANNELS)
    # The fmt chunk: its size (52), format version 1, format 0 (raw DSD),
    # channel type 2 (stereo), channels, sample rate, 1 bit per sample, sample
    # count, block size, and 4 reserved bytes.
    fmt_chunk = b"fmt " + struct.pack(
        "<QIIIIIIQI4x",
        52,
        1,
        0,
        2,
        _DSD_CHANNELS,
        _DSD_SAMPLE_RATE,
        1,
        samples,
        4096,
    )
    data_chunk = b"data" + struct.pack("<Q", 12 + len(data)) + data
    # The DSD chunk: its size (28), the file size, and the offset of the
    # metadata, which stays 0 until mutagen writes the tags.
    total_size = 28 + len(fmt_chunk) + len(data_chunk)
    dsd_chunk = b"DSD " + struct.pack("<QQQ", 28, total_size, 0)
    return dsd_chunk + fmt_chunk + data_chunk


def _dff_chunk(chunk_id: bytes, body: bytes) -> bytes:
    # DSDIFF is big-endian, with 8-byte sizes. A body of odd length gets one
    # padding byte, which the size does not count.
    return chunk_id + struct.pack(">Q", len(body)) + body + bytes(len(body) % 2)


def _dff_bytes() -> bytes:
    version = _dff_chunk(b"FVER", struct.pack(">I", 0x01050000))
    sample_rate = _dff_chunk(b"FS  ", struct.pack(">I", _DSD_SAMPLE_RATE))
    channels = _dff_chunk(b"CHNL", struct.pack(">H", _DSD_CHANNELS) + b"SLFTSRGT")
    name = b"not compressed"
    compression = _dff_chunk(b"CMPR", b"DSD " + bytes([len(name)]) + name)
    properties = _dff_chunk(b"PROP", b"SND " + sample_rate + channels + compression)
    # mutagen computes the length of a DSDIFF file from the size of its audio
    # data, not from a sample count, so the data is complete: one byte for
    # each 8 samples of each channel.
    data_size = _DSD_SAMPLE_RATE * _DSD_SECONDS // 8 * _DSD_CHANNELS
    audio = _dff_chunk(b"DSD ", _DSD_SILENCE * data_size)
    return _dff_chunk(b"FRM8", b"DSD " + version + properties + audio)


@pytest.fixture
def make_dsd_file(tmp_path):
    """Write a DSF or DFF file of DSD silence, with ID3 tags.

    ffmpeg decodes DSD but cannot encode it, so the tests build these files.
    The extension of the name chooses the format. The tags follow the fixture
    files, with the extension in the title.
    """
    formats = {".dsf": (_dsf_bytes, DSF), ".dff": (_dff_bytes, DSDIFF)}

    def _make_dsd_file(name: str) -> Path:
        path = tmp_path / name
        extension = path.suffix.lower()
        build, file_type = formats[extension]
        path.write_bytes(build())
        audio = file_type(path)
        audio.add_tags()
        audio.tags.add(TIT2(encoding=3, text=f"Test Track {extension[1:].upper()}"))
        audio.tags.add(TPE1(encoding=3, text="Music Zamlr Fixtures"))
        audio.tags.add(TALB(encoding=3, text="Synthetic Test Album"))
        audio.tags.add(TDRC(encoding=3, text="2026"))
        audio.tags.add(TRCK(encoding=3, text="3/10"))
        audio.save()
        return path

    return _make_dsd_file


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


@pytest.fixture(autouse=True)
def fpcalc_is_installed(monkeypatch):
    # Every diff through the endpoint asks PATH for fpcalc. Without this, the
    # tests that need the fingerprint tier fail on any machine that lacks it,
    # while CI, which installs fpcalc, stays green. Autouse, so a new diff test
    # cannot forget it. A test about the missing case patches it to False; its
    # own patch runs later and wins.
    #
    # main's name, not fingerprinting's. main.py imported fpcalc_available into
    # its own namespace, so patching the original leaves that reference alone.
    monkeypatch.setattr("main.fpcalc_available", lambda: True)


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
            file_mtime_ns=0,
            file_hash=None,
            fingerprint=None,
            fingerprint_length=None,
            fingerprint_algorithm=None,
            collection_id=1,
        )
        unknown = set(overrides) - set(defaults)
        if unknown:
            raise TypeError(f"make_track got unknown field(s): {sorted(unknown)}")
        defaults.update(overrides)
        return Track(**defaults)

    return _make_track


@pytest.fixture
def fake_fingerprint():
    """Build a repeatable list of 32-bit values that stands in for a real one.

    Seeded rather than random, so a failure reproduces exactly. Two different
    seeds stand in for two unrelated recordings, and the same seed twice
    stands in for two encodings of one recording.

    The default of 200 frames is above MIN_OVERLAP_FRAMES on purpose. A
    shorter list makes compare_fingerprints answer None for every pair, so a
    test built on one would pass without comparing anything.
    """

    def _fake_fingerprint(seed: int, frames: int = 200) -> list[int]:
        rng = random.Random(seed)
        return [rng.getrandbits(32) for _ in range(frames)]

    return _fake_fingerprint


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

    The scan endpoints, /api/diff and both import endpoints stream
    Server-Sent Events rather than answer with JSON. The final frame carries
    the result, so a test reads .done where it would otherwise read
    response.json().

    The method is a parameter because the scans and imports are POSTs while
    the diff is a GET: the diff's only write is caching hashes onto rows that
    already exist, which is a cache fill rather than a state change.

    Success paths only. A request that fails validation never opens a stream,
    so those tests keep using client.get or client.post and a status code —
    which is what makes them the tests for "validate first".
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


@pytest.fixture(scope="session")
def launch_environment():
    """Build the environment for a child process that reads ZAMLR_ names.

    Session scope because it holds no state and because a module-scoped
    fixture cannot depend on a narrower one: test_env_wiring's child runs
    once per module and still has to reach this.

    The copy is what matters. env= replaces the whole environment rather
    than adding to it, and a child on Windows with nothing in its
    environment cannot start. Every ZAMLR_ name is dropped first, so a
    variable left set in the terminal that runs pytest cannot decide what
    a test proves.
    """

    def build(**variables: str) -> dict[str, str]:
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("ZAMLR_")
        }
        environment.update(variables)
        return environment

    return build


@pytest.fixture(scope="session")
def read_port_line():
    """Read a child's output until it announces its port.

    The announcement is found by its prefix rather than by its position,
    because uvicorn writes its own startup lines. Everything read on the
    way is kept for the failure message, which is the only place a child's
    own traceback appears.
    """

    def read(process: subprocess.Popen) -> int:
        seen = []
        for line in process.stdout:
            if line.startswith(PORT_LINE_PREFIX):
                return int(line.removeprefix(PORT_LINE_PREFIX).strip())
            seen.append(line)
        raise AssertionError(
            "The server never announced a port. Its output was:\n" + "".join(seen)
        )

    return read
