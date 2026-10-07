import asyncio
import json
import logging
import ntpath
import os
import shutil
from collections.abc import Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from functools import partial

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from database import apply_migrations, create_collection, get_session
from enums import ActionType, Bucket, ImportPhase, OperationStatus
from fingerprinting import fpcalc_available
from format_order import default_tiers, effective_tiers, tiers_to_ranks, validate_tiers
from importing import (
    ExecuteProgress,
    OperationResult,
    PlannedOperation,
    execute_plan,
    plan_import,
)
from launch_settings import read_launch_settings
from matching import (
    FORMAT_RANK,
    DiffProgress,
    Match,
    MatchResult,
    classify_pairing,
    is_lossy,
    match_collections,
)
from models import Collection, FormatOrderRow, Track
from scanner import ScanProgress, scan_folder
from schemas import (
    CollectionRead,
    DiffProgressRead,
    DiffResultRead,
    FormatOrderRead,
    FormatOrderWrite,
    ImportPreviewRead,
    ImportProgressRead,
    ImportRequest,
    ImportResultRead,
    OperationResultRead,
    ScanProgressRead,
    ScanRequest,
    ScanResultRead,
)
from token_middleware import TokenMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Bring the schema up to date before the first request.

    Until this existed, only scanner.py's CLI main() ever created the tables,
    so the server could not start from nothing: delete db/music.db and SQLite
    obligingly creates an empty file on the first connection, with no tables
    in it, and every request then fails on "no such table". Running the
    migrations on every start costs one query against alembic_version once
    the database is at head.

    Here rather than in serve.py, so that every way of starting the server
    passes through it — `fastapi dev`, the packaged entry point, and the
    tests that run the application in a child process. A migration step the
    launcher owns is a migration step one launcher can skip.

    An exception from here stops the application from starting, which is the
    intent. A backend that could not bring the database to the schema its
    queries assume has nothing safe to answer with.

    Note for the tests: conftest.py replaces database.engine with one that
    raises on connect, and this would reach it. It does not today, because
    the client fixture builds TestClient(app) without using it as a context
    manager, and TestClient only runs lifespan inside a `with`. Changing that
    means giving the fixture a real engine here too.
    """
    apply_migrations()
    yield


# Read once, here, because add_middleware runs at import: by the time any
# request arrives the origins are already baked into the middleware. Changing
# the variable therefore needs the process restarted, and no test can vary it
# in-process — the environment wiring is checked by hand instead.
launch_settings = read_launch_settings(os.environ)

app = FastAPI(lifespan=lifespan)


if launch_settings.token is not None:
    app.add_middleware(TokenMiddleware, secret=launch_settings.token)


app.add_middleware(
    CORSMiddleware,
    allow_origins=launch_settings.allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def get_health():
    return {"status": "ok"}


@app.get("/api/collections", response_model=list[CollectionRead])
def list_collections(session: Session = Depends(get_session)):
    return session.exec(select(Collection)).all()


@dataclass
class DiffResult:
    match_results: MatchResult
    match_counts: dict[str, int]


def _load_collections(
    session: Session, mine_id: int, theirs_id: int
) -> tuple[Collection, Collection]:
    """Load both collections, rejecting an unknown id or a self-comparison."""
    if mine_id == theirs_id:
        raise HTTPException(
            status_code=400, detail="Cannot diff a collection against itself."
        )
    mine = session.get(Collection, mine_id)
    theirs = session.get(Collection, theirs_id)
    if mine is None or theirs is None:
        raise HTTPException(status_code=404, detail="Collection not found.")
    return mine, theirs


def _run_diff(
    session: Session,
    mine_collection: Collection,
    theirs_collection: Collection,
    # Told, never looked up here, like fingerprints_available below: both
    # callers read it from the session they own, and the import reads it once
    # for this call and for the review answer it judges itself.
    format_ranks: Mapping[str, int],
    on_progress: Callable[[DiffProgress], None] | None = None,
) -> MatchResult:
    tracks_mine = session.exec(
        select(Track).where(Track.collection_id == mine_collection.id)
    ).all()
    tracks_theirs = session.exec(
        select(Track).where(Track.collection_id == theirs_collection.id)
    ).all()
    # Asked here, once per diff, because this is the one place both callers
    # share: the diff stream, and the import, which recomputes the diff on the
    # server before it plans. Asked in the stream alone, the import would
    # still try fpcalc for every track and log a warning for each.
    match_result = match_collections(
        tracks_mine,
        tracks_theirs,
        on_progress=on_progress,
        fingerprints_available=fpcalc_available(),
        format_ranks=format_ranks,
    )
    session.commit()  # persist the hashes the matcher computed
    return match_result


PROGRESS_INTERVAL_SECONDS = 0.2


@dataclass
class ImportProgress:
    """Progress for both import endpoints, across both of their phases.

    Generic field names, unlike DiffProgress, because this describes two
    different things depending on the phase: tracks compared, then files
    copied. A name like theirs_processed_count would be a lie in the second.

    The phase says which stage the work has reached, not which endpoint was
    called — the client already knows that, having made the request. What it
    cannot otherwise know is whether an execute is still comparing or has
    begun writing to disk, which is the difference between a run that can be
    abandoned harmlessly and one that cannot.
    """

    phase: ImportPhase
    processed_count: int
    total_count: int
    current_path: str | None = None


# What a worker reports as it goes. Unrelated shapes; the union exists only so
# _stream can hold one without caring which it has.
#
# ExecuteProgress is deliberately absent even though execute_plan reports one.
# It never reaches _stream: _execute_worker converts it, and DiffProgress, into
# ImportProgress before either leaves the worker.
Progress = ScanProgress | DiffProgress | ImportProgress
ProgressCallback = Callable[[Progress], None]


def _sse(event: str, payload: dict) -> str:
    """One Server-Sent Events frame: an event line, a data line, a blank line.

    json.dumps escapes every newline inside a string, so no payload can split
    a frame in two. That is why a single data: line is always enough here.
    """
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


def _scan_worker(
    root_path: str, collection_id: int, engine, on_progress: ProgressCallback
) -> tuple[str, dict]:
    """Scan, and build the frame that ends the stream. Runs on a worker thread.

    The payload is built in here, while the session is still open.
    ScanResult.collection is an ORM object, and serializing it after its
    session closes raises DetachedInstanceError.

    Every exception is caught, which the project's convention normally
    forbids. It has to be: StreamingResponse has already sent 200 by the time
    this runs, so a failure has nowhere to go except the stream itself. The
    traceback still reaches the server log, so a bug stays as loud as it was,
    only in a different place.
    """
    try:
        with Session(engine) as session:
            scan_result = scan_folder(
                root_path, collection_id, session, on_progress=on_progress
            )
            payload = ScanResultRead.model_validate(scan_result).model_dump(mode="json")
        return "done", payload
    except Exception as error:
        logging.exception("Scan of %s failed", root_path)
        return "error", {"detail": str(error)}


def _diff_worker(
    mine_id: int, theirs_id: int, engine, on_progress: ProgressCallback
) -> tuple[str, dict]:
    """Diff, and build the frame that ends the stream. Runs on a worker thread.

    The collections are loaded again here rather than handed in. The endpoint
    already loaded them to validate the request, but those objects belong to
    the request's session and to the request's thread, and DiffResultRead
    reaches every matched Track on both sides. Two lookups by primary key is
    the price of keeping the guards ahead of the stream and the ORM objects
    inside one thread.

    The broad catch is the same deliberate exception as in _scan_worker, and
    it logs the two ids rather than the collections: if _load_collections is
    what raised, no collection was ever bound, and reading .name in here would
    replace the real failure with an UnboundLocalError.
    """
    try:
        with Session(engine) as session:
            mine_collection, theirs_collection = _load_collections(
                session, mine_id, theirs_id
            )
            match_result = _run_diff(
                session,
                mine_collection,
                theirs_collection,
                # Read here, inside the session this thread owns. The
                # request's session may not cross into the worker, which is
                # why the collections above are loaded again as well.
                format_ranks=_format_ranks(session),
                on_progress=on_progress,
            )
            diff_result = DiffResult(
                match_results=match_result,
                match_counts=dict(
                    missing=len(match_result.missing),
                    upgrade_available=len(match_result.upgrade_available),
                    already_have=len(match_result.already_have),
                    needs_review=len(match_result.needs_review),
                    only_in_mine=len(match_result.only_in_mine),
                ),
            )
            payload = DiffResultRead.model_validate(diff_result).model_dump(mode="json")
        return "done", payload
    except Exception as error:
        logging.exception("Diff of collections %s and %s failed", mine_id, theirs_id)
        return "error", {"detail": str(error)}


def _check_destination_root(destination_root: str) -> None:
    """Reject a destination we cannot write to. Raises, or returns nothing.

    Called twice per import request, and both calls earn their place. The
    endpoint calls it before opening the stream, so a bad path is a 400 the
    client can read; _build_plan calls it again on the worker thread, so the
    function is safe to call on its own and its own tests still hold.
    """
    if not os.path.isdir(destination_root):
        raise HTTPException(
            status_code=400,
            detail="Destination root does not exist or is not a directory.",
        )
    if not os.access(destination_root, os.W_OK):
        raise HTTPException(status_code=400, detail="Destination root is not writable.")


def _comparing_reporter(
    on_progress: ProgressCallback,
) -> Callable[[DiffProgress], None]:
    """Adapt what _build_plan reports into what the stream carries.

    match_collections counts tracks of theirs and knows nothing about imports;
    the stream carries one shape for both phases. Translating here is what
    keeps matching.py ignorant of ImportPhase and of the schema layer.
    """

    def report(progress: DiffProgress) -> None:
        on_progress(
            ImportProgress(
                phase=ImportPhase.COMPARING,
                processed_count=progress.theirs_processed_count,
                total_count=progress.theirs_count,
                current_path=progress.current_path,
            )
        )

    return report


def _copying_reporter(
    on_progress: ProgressCallback,
) -> Callable[[ExecuteProgress], None]:
    """The same adaptation for the second phase, from importing.py's shape.

    total_count drops from the number of tracks compared to the number of
    operations planned, which is correct and will look like a reset in the UI.
    The phase field is what tells the reader those two totals count different
    things.
    """

    def report(progress: ExecuteProgress) -> None:
        on_progress(
            ImportProgress(
                phase=ImportPhase.COPYING,
                processed_count=progress.operations_processed_count,
                total_count=progress.operations_count,
                current_path=progress.current_path,
            )
        )

    return report


def _count_operations(operations: list[PlannedOperation]) -> dict[str, int]:
    return {
        "copy": sum(1 for op in operations if op.action == ActionType.COPY),
        "delete": sum(1 for op in operations if op.action == ActionType.DELETE),
        "move": sum(1 for op in operations if op.action == ActionType.MOVE),
        "overwrites": sum(1 for op in operations if op.overwrites),
    }


def _same_drive(one: str, other: str) -> bool:
    """Say whether two paths name the same drive, by their spelling alone.

    `ntpath` rather than `os.path`, which is the same function on Windows
    and `posixpath` everywhere else. The paths this compares come out of a
    Windows user's database whatever machine is reading them, and
    `posixpath.splitdrive` finds no drive in any of them: every path would
    answer "same drive" and the caller would stop counting. A test written
    with drive letters would then assert nothing under Linux CI.

    Spelling is all it looks at, because the caller's whole value is that it
    touches no disk. A folder on C: that is really a mount point for another
    volume reads as C: here, and a move into it is not counted.
    """
    return (
        ntpath.splitdrive(one)[0].casefold() == ntpath.splitdrive(other)[0].casefold()
    )


def _bytes_required(operations: list[PlannedOperation], tracks: list[Track]) -> int:
    bytes_required = 0
    tracks_by_file_path = {os.path.normpath(t.file_path): t for t in tracks}
    for operation in operations:
        if operation.action == ActionType.COPY:
            # file_size is what the scanner recorded, so the whole sum costs no
            # disk I/O. It goes stale if a file changed since, and that is the
            # deliberate trade: a total a few megabytes out beats one that stats
            # several hundred files on a drive that may be slow, asleep, or
            # across a network.
            bytes_required += tracks_by_file_path[
                os.path.normpath(operation.source)
            ].file_size
        elif operation.action == ActionType.MOVE and not _same_drive(
            operation.source, operation.destination
        ):
            # A move inside one drive renames and no bytes travel. Across
            # drives it copies into _superseded and deletes the original, so
            # the destination holds both the replacement and the file it
            # replaced, and the destination is the only drive this total is
            # about. Left uncounted, the one case where the warning errs
            # toward silence.
            #
            # No guard for a destination of None, although the field allows
            # it: plan_move always sets one, so a move without a destination
            # is this code being wrong, and splitdrive raising TypeError
            # says so where a default would quietly undercount.
            bytes_required += tracks_by_file_path[
                os.path.normpath(operation.source)
            ].file_size
    return bytes_required


def _preview_worker(
    request: ImportRequest, engine, on_progress: ProgressCallback
) -> tuple[str, dict]:
    """Plan an import without touching anything. Runs on a worker thread.

    One phase only: the whole cost is the diff _build_plan recomputes, because
    the server never trusts a classification the client sends.
    It still reports a phase, so both import endpoints share one payload shape
    and one progress component on the frontend.

    Most of _build_plan's rejections happen after that diff and cannot be HTTP
    status codes — 200 has gone out by then — so they arrive as error frames
    with the same message. Only the request-shaped checks stay statuses, and
    the endpoint runs those before the stream opens.
    """
    try:
        with Session(engine) as session:
            import_plan = _build_plan(
                request, session, on_progress=_comparing_reporter(on_progress)
            )
            bytes_free = shutil.disk_usage(request.destination_root).free
            preview = PreviewResult(
                operations=import_plan.operations,
                upgrades=import_plan.upgrades,
                operation_counts=_count_operations(import_plan.operations),
                bytes_required=import_plan.bytes_required,
                bytes_free=bytes_free,
            )
            payload = ImportPreviewRead.model_validate(preview).model_dump(mode="json")
        return "done", payload
    except Exception as error:
        logging.exception(
            "Preview of collection %s into %s failed",
            request.theirs_collection_id,
            request.destination_root,
        )
        return "error", {"detail": str(error)}


def _execute_worker(
    request: ImportRequest, engine, on_progress: ProgressCallback
) -> tuple[str, dict]:
    """Plan an import and carry it out. Runs on a worker thread.

    Two phases, one stream, one done frame. The plan is rebuilt here rather
    than carried over from a preview: the server recomputes rather than
    trusting a client-supplied classification, and there is no preview
    token, so an execute cannot assume a preview ever happened.

    The phases differ in more than duration. Nothing on disk changes during
    the first; everything does during the second, which is why the frames say
    which one is running rather than only how far along it is.
    """
    try:
        with Session(engine) as session:
            import_plan = _build_plan(
                request, session, on_progress=_comparing_reporter(on_progress)
            )
            operation_results = execute_plan(
                import_plan.operations, on_progress=_copying_reporter(on_progress)
            )

            # Successful deletes and moves leave rows pointing at files that no
            # longer exist; the next diff would offer the same upgrade again and
            # then fail on the delete. Copies deliberately get no rows: the
            # destination root is any folder the user picked, so nothing
            # guarantees it sits inside mine's collection tree. A re-scan is how
            # they appear.
            for result in operation_results:
                if (
                    result.status == OperationStatus.SUCCESS
                    and result.operation.action in (ActionType.DELETE, ActionType.MOVE)
                ):
                    stale_track = session.exec(
                        select(Track).where(
                            Track.collection_id == request.mine_collection_id,
                            Track.file_path == result.operation.source,
                        )
                    ).first()
                    if stale_track is not None:
                        session.delete(stale_track)
            session.commit()

            (log_path, log_error) = _write_import_log(
                request.destination_root, operation_results
            )
            import_result = ImportResult(
                operations=operation_results,
                status_counts={
                    "success": sum(
                        1
                        for r in operation_results
                        if r.status == OperationStatus.SUCCESS
                    ),
                    "failed": sum(
                        1
                        for r in operation_results
                        if r.status == OperationStatus.FAILED
                    ),
                    "skipped": sum(
                        1
                        for r in operation_results
                        if r.status == OperationStatus.SKIPPED
                    ),
                },
                log_path=log_path,
                log_error=log_error,
            )
            payload = ImportResultRead.model_validate(import_result).model_dump(
                mode="json"
            )
        return "done", payload
    except Exception as error:
        logging.exception(
            "Import of collection %s into %s failed",
            request.theirs_collection_id,
            request.destination_root,
        )
        return "error", {"detail": str(error)}


def _stream(
    run: Callable[[ProgressCallback], tuple[str, dict]],
    progress_schema: type[BaseModel],
) -> StreamingResponse:
    """Run blocking work on a worker thread and stream its progress as SSE.

    Every streaming endpoint ends in a call to this, so none of them can drift
    apart on the frame format, the poll interval or the failure handling.

    `run` is the only thing that differs between them. It is handed the
    progress callback and returns the event name and payload of the final
    frame. Passing the work in, rather than passing a description of which
    work to do, is what keeps this function from having to know that scans and
    diffs exist.

    Nothing about a request's Session may cross in here. The worker opens its
    own; the engine is the one database object safe to share, because it owns
    the pool and the Session is what is not thread-safe.
    """
    latest: Progress | None = None

    def remember(progress: Progress) -> None:
        # One rebinding per call, so the reader below always sees a whole
        # object and never a half-written one. Progress is a state rather than
        # a log: only the newest value has any use, so this overwrites instead
        # of collecting a backlog that nobody reads and that would hold one
        # object per file for the length of the work.
        nonlocal latest
        latest = progress

    async def frames():
        loop = asyncio.get_running_loop()
        # get_running_loop belongs in here, not in the body above: _stream runs
        # on the request thread, which has no loop, while this generator is
        # iterated by Starlette on the event loop.
        future = loop.run_in_executor(None, run, remember)
        while not future.done():
            # This sleep is what hands control back to the event loop, so the
            # server still answers other requests while a drive is read.
            await asyncio.sleep(PROGRESS_INTERVAL_SECONDS)
            progress = latest
            # None until the first report lands, and fast work can finish
            # before any arrive, so a stream with no progress frame at all is
            # normal rather than a fault.
            if progress is not None:
                yield _sse(
                    "progress",
                    progress_schema.model_validate(progress).model_dump(mode="json"),
                )
        # run catches its own failures, so this never re-raises. That also
        # means a client that disconnects midway leaves no exception sitting
        # unretrieved on the future.
        event, payload = future.result()
        yield _sse(event, payload)

    return StreamingResponse(
        frames(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/diff")
def diff_collections(
    mine: int,
    theirs: int,
    session: Session = Depends(get_session),
):
    # Validated here, on the request thread, so a bad request still gets a real
    # 400 or 404. Once _stream returns, 200 has been sent and cannot be undone.
    mine_collection, theirs_collection = _load_collections(session, mine, theirs)

    return _stream(
        partial(
            _diff_worker,
            mine_collection.id,
            theirs_collection.id,
            session.get_bind(),
        ),
        DiffProgressRead,
    )


def _describe_track(track: Track) -> str:
    """Name a track for an error message.

    The file name is included even when tags are present, because the tracks
    that collide in these messages got there by matching each other on
    normalized artist and title — so their tags are identical, and the file
    name is the only thing that tells the reader which one is meant.
    """
    if track.title and track.artist:
        return f"{track.artist} — {track.title} ({track.file_name})"
    return track.file_name


def _describe_track_id(session: Session, track_id: int) -> str:
    """Name a track the client referred to, which may not exist at all."""
    track = session.get(Track, track_id)
    return _describe_track(track) if track is not None else f"track {track_id}"


@dataclass
class BuiltPlan:
    operations: list[PlannedOperation]
    upgrades: list[Match]
    bytes_required: int


def _build_plan(
    request: ImportRequest,
    session: Session,
    on_progress: Callable[[DiffProgress], None] | None = None,
) -> BuiltPlan:
    """Load, diff, filter, and plan. Shared by preview and execute.

    The request carries track ids, not classifications: the client says
    which tracks of theirs to act on, and the server decides for itself
    which are missing and which are upgrades. Accepting a client-supplied
    pairing would let a row-index bug in the grid delete the wrong file of
    mine, since the server would have nothing to check it against.

    The cost is a full diff, hashing included, on every request. If that
    becomes the bottleneck, persist the diff and reference it by id rather
    than moving classification to the client.
    """
    mine_collection_id = request.mine_collection_id
    theirs_collection_id = request.theirs_collection_id
    track_ids = set(request.track_ids)
    destination_root = request.destination_root

    _check_destination_root(destination_root)

    mine_collection, theirs_collection = _load_collections(
        session, mine_collection_id, theirs_collection_id
    )
    # Once, for the diff below and for the review answers further down. Two
    # reads could straddle a save and answer differently, and the request
    # would then judge one pairing by one order and the next by another.
    format_ranks = _format_ranks(session)
    match_result = _run_diff(
        session,
        mine_collection,
        theirs_collection,
        format_ranks=format_ranks,
        on_progress=on_progress,
    )

    missing: list[Track] = []
    resolved_to_already_have: list[Track] = []
    upgrade_available: list[Match] = []
    placed_ids: set[int] = set()
    resolved_theirs_ids: set[int] = set()

    ambiguous_by_theirs_id = {a.theirs.id: a for a in match_result.needs_review}

    for resolution in request.resolutions:
        if resolution.theirs_id in resolved_theirs_ids:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Two conflicting decisions for "
                    f"{_describe_track(ambiguous_by_theirs_id[resolution.theirs_id].theirs)}. "
                    f"Send one decision per track."
                ),
            )
        if resolution.theirs_id not in ambiguous_by_theirs_id:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{_describe_track_id(session, resolution.theirs_id)} is not "
                    f"awaiting review. The comparison may be out of date — run "
                    f"Compare again."
                ),
            )
        candidates_by_id = {
            c.mine.id: c.mine
            for c in ambiguous_by_theirs_id[resolution.theirs_id].candidates
        }
        theirs = ambiguous_by_theirs_id[resolution.theirs_id].theirs
        # This check prevents a frontend bug from picking an arbitrary file for upgrade.
        # It can pick the wrong candidate among genuine candidates only.
        if (
            resolution.mine_id is not None
            and resolution.mine_id not in candidates_by_id
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{_describe_track_id(session, resolution.mine_id)} is not one "
                    f"of the files matched to {_describe_track(theirs)}. Run "
                    f"Compare again and choose from the listed files."
                ),
            )
        resolved_theirs_ids.add(resolution.theirs_id)

        if resolution.theirs_id in track_ids:
            if resolution.mine_id is None:
                missing.append(theirs)
                placed_ids.add(resolution.theirs_id)
            else:
                mine = candidates_by_id[resolution.mine_id]
                pairing_bucket = classify_pairing(
                    mine_track=mine, theirs_track=theirs, format_ranks=format_ranks
                )
                if pairing_bucket == Bucket.UPGRADE_AVAILABLE:
                    upgrade_available.append(Match(mine=mine, theirs=theirs))
                    placed_ids.add(resolution.theirs_id)
                elif pairing_bucket == Bucket.ALREADY_HAVE:
                    resolved_to_already_have.append(theirs)

    for track in match_result.missing:
        if track.id in track_ids:
            missing.append(track)
            placed_ids.add(track.id)

    for match in match_result.upgrade_available:
        if match.theirs.id in track_ids:
            upgrade_available.append(match)
            placed_ids.add(match.theirs.id)

    if resolved_to_already_have:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Nothing to import for "
                f"{', '.join(_describe_track(t) for t in resolved_to_already_have)}: "
                f"the {'files' if len(resolved_to_already_have) > 1 else 'file'} you "
                f"chose is at least as good as theirs. Pick a different file, or deselect "
                f"the track."
            ),
        )

    rejected_tracks: list[Track] = []
    rejected_ids = sorted(track_ids - placed_ids)

    if rejected_ids:
        for rejected_id in rejected_ids:
            rejected_track = session.get(Track, rejected_id)
            if rejected_track:
                rejected_tracks.append(rejected_track)
        raise HTTPException(
            status_code=400,
            detail=(
                f"Not import candidates: "
                f"{', '.join(_describe_track(t) for t in rejected_tracks)}. They "
                f"may already be covered, still need review, or the comparison may be out "
                f"of date — run Compare again and retry."
            ),
        )

    # No two planned upgrades may supersede the same file of mine. This
    # catches both halves of double-booking in one check: two resolutions
    # naming the same file, and a resolution colliding with a confident
    # upgrade that is also selected — both end up as two Matches sharing a
    # mine.id.
    #
    # Scoped to the upgrades actually being planned, deliberately. An
    # unselected upgrade and a resolution that classified as already-have
    # both produce no operation, so neither can collide with anything;
    # checking against the matcher's whole consumed set would reject
    # requests that are perfectly safe.
    claimed_by: dict[int, Track] = {}
    for match in upgrade_available:
        first_claim = claimed_by.get(match.mine.id)
        if first_claim is not None:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{_describe_track(first_claim)} and "
                    f"{_describe_track(match.theirs)} would both replace your "
                    f"file {match.mine.file_name}. Choose a different file for "
                    f"one of them."
                ),
            )
        claimed_by[match.mine.id] = match.theirs

    try:
        import_plan = plan_import(
            missing=missing,
            upgrades=upgrade_available,
            source_root=theirs_collection.root_path,
            destination_root=destination_root,
            structure_mode=request.structure_mode,
            upgrade_action=request.upgrade_action,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    # Mine as well as theirs: a move's source is a track of mine, and a
    # lookup that cannot find it raises rather than returning nothing. This
    # runs on the import path too, where _build_plan's total is discarded —
    # so a list short of one track fails an import instead of an estimate.
    # Unconditional rather than only for the move action, since an extra
    # entry in the map costs nothing and a condition is one more thing to
    # keep in step with the planner.
    bytes_required = _bytes_required(
        import_plan,
        [
            *missing,
            *(m.theirs for m in upgrade_available),
            *(m.mine for m in upgrade_available),
        ],
    )
    return BuiltPlan(
        operations=import_plan,
        upgrades=upgrade_available,
        bytes_required=bytes_required,
    )


@dataclass
class PreviewResult:
    operations: list[PlannedOperation]
    upgrades: list[Match]
    operation_counts: dict[str, int]
    bytes_required: int
    bytes_free: int


@app.post("/api/import/preview")
def preview_import(
    request: ImportRequest,
    session: Session = Depends(get_session),
):
    # Validated here, on the request thread, so a bad request still gets a
    # real 400 or 404. Once _stream returns, 200 has been sent and cannot be
    # undone — every later rejection arrives as an error frame instead.
    _check_destination_root(request.destination_root)
    _load_collections(session, request.mine_collection_id, request.theirs_collection_id)

    return _stream(
        partial(_preview_worker, request, session.get_bind()),
        ImportProgressRead,
    )


@dataclass
class ImportResult:
    operations: list[OperationResult]
    status_counts: dict[str, int]
    log_path: str | None = None
    log_error: str | None = None


# The shape of the file _write_import_log leaves in the destination folder.
# Raise it whenever a key is added, removed or changes meaning: the file sits
# in the user's music folder long after the version that wrote it has been
# replaced, and this number is the only thing a later reader can go by.
IMPORT_LOG_FORMAT_VERSION = 1


def _write_import_log(
    destination_root: str, results: list[OperationResult]
) -> tuple[str | None, str | None]:
    """Leave a record of an import beside the files it wrote.

    An object at the top, not a bare list of operations. A list has no room
    for a key, so a format that began as one could only ever gain a version
    by turning into an object and teaching every reader both shapes.

    written_at repeats the timestamp in the filename on purpose: the user may
    rename the file, and its content should still say when it was made. One
    clock reading serves both, so the two cannot straddle a second boundary
    and disagree.
    """
    log_path = None
    log_error = None
    try:
        written_at = datetime.now()
        candidate_path = os.path.normpath(
            os.path.join(
                destination_root,
                "import_log_" + written_at.strftime("%Y%m%d-%H%M%S") + ".json",
            )
        )
        payload = {
            "format_version": IMPORT_LOG_FORMAT_VERSION,
            "written_at": written_at.isoformat(timespec="seconds"),
            "operations": [
                OperationResultRead.model_validate(r).model_dump(mode="json")
                for r in results
            ],
        }
        with open(candidate_path, "w", encoding="utf-8") as log_file:
            json.dump(payload, log_file, indent=2, ensure_ascii=False)
        log_path = candidate_path
    except OSError as error:
        log_error = str(error)

    return log_path, log_error


@app.post("/api/import/execute")
def execute_import(
    request: ImportRequest,
    session: Session = Depends(get_session),
):

    _check_destination_root(request.destination_root)
    _load_collections(session, request.mine_collection_id, request.theirs_collection_id)

    # One call, one stream, one done frame. The two phases are not two
    # streams: _execute_worker runs the diff and then the copying inside a
    # single blocking function, and both report through the same callback, so
    # a phase change is only the next value in the snapshot cell that _stream
    # already polls.
    return _stream(
        partial(_execute_worker, request, session.get_bind()),
        ImportProgressRead,
    )


@app.post("/api/collections/scan")
def scan_collection(
    request: ScanRequest,
    session: Session = Depends(get_session),
):
    if not os.path.isdir(request.root_path):
        raise HTTPException(
            status_code=400,
            detail="Collection path does not exist or is not a directory.",
        )
    clash = next(
        (
            existing
            for existing in session.exec(select(Collection)).all()
            if existing.name.casefold() == request.name.casefold()
        ),
        None,
    )
    if clash is not None:
        raise HTTPException(
            status_code=400,
            detail=f"A collection named {clash.name!r} already exists.",
        )

    collection = create_collection(
        Collection(
            name=request.name,
            root_path=os.path.normpath(request.root_path),
            last_scanned_at=None,
        ),
        session,
    )

    return _stream(
        partial(_scan_worker, collection.root_path, collection.id, session.get_bind()),
        ScanProgressRead,
    )


@app.post("/api/collections/{collection_id}/rescan")
def rescan_collection(
    collection_id: int,
    session: Session = Depends(get_session),
):
    collection = session.get(Collection, collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail="Collection not found.")

    if not os.path.isdir(collection.root_path):
        raise HTTPException(
            status_code=400,
            detail="Collection path not found. It may not be mounted.",
        )

    return _stream(
        partial(_scan_worker, collection.root_path, collection.id, session.get_bind()),
        ScanProgressRead,
    )


def _format_order_state(session: Session) -> FormatOrderRead:
    """Read the saved order and answer with what the matcher would rank by.

    Both endpoints answer with this, so a PUT reports the state a later GET
    returns. They differ for a PUT of the default order, which saves nothing:
    a body built from the request would claim a saved order that the server
    does not hold.

    No rows means no saved order, so max() needs the default: the timestamp
    is then None, which is how the editor knows it is showing the default.
    """
    rows = session.exec(select(FormatOrderRow)).all()
    ranks = {row.format: row.rank for row in rows}
    tiers, placed = effective_tiers(ranks)
    updated_at = max((row.updated_at for row in rows), default=None)
    # Sent so the editor can refuse a move that would make a lossy format tie
    # with a lossless one. Derived here rather than listed again in the
    # browser, where it would drift from the scanner as formats are added.
    lossy_formats = [name for name in FORMAT_RANK if is_lossy(name)]
    return FormatOrderRead(
        tiers=tiers,
        default_tiers=default_tiers(),
        placed=placed,
        updated_at=updated_at,
        lossy_formats=lossy_formats,
    )


def _format_ranks(session: Session) -> dict[str, int]:
    """Return the ranks a comparison should use, from the saved order.

    Built from the tiers the GET answers with, not from the rows: those tiers
    are the effective ones, with a format the saved order never named already
    placed. Read straight from the rows, such a format would rank 0 in a
    comparison while the editor showed it inside a tier, and 0 is the rank of
    a format the app cannot read at all.
    """
    return tiers_to_ranks(_format_order_state(session).tiers)


@app.get("/api/settings/format-order", response_model=FormatOrderRead)
def list_format_order(session: Session = Depends(get_session)):
    return _format_order_state(session)


@app.put("/api/settings/format-order", response_model=FormatOrderRead)
def save_format_order(
    body: FormatOrderWrite,
    session: Session = Depends(get_session),
):
    """Replace the saved format order, or clear it when it is the default.

    A PUT says what the whole order is, so validate_tiers refuses an order
    that leaves a format out rather than filling it in. It runs before
    anything is deleted: a refused order must leave the saved one exactly as
    it was.

    The rows are replaced, never updated in place. An order saved earlier can
    name a format that this one does not, and an in-place update would leave
    that row behind to outrank something for ever.

    An order equal to the default is stored as no rows at all, which is what
    reset writes. Storing it would freeze today's default, so a later release
    that improves the default order would never reach a user who once pressed
    reset.
    """
    try:
        validate_tiers(body.tiers)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    for row in session.exec(select(FormatOrderRow)).all():
        session.delete(row)
    # Sends the deletes before the inserts below, rather than leaving the
    # order of the two to the session. Every PUT after the first writes the
    # formats the old rows already hold, and SQLite refuses a duplicate
    # primary key. SQLAlchemy orders the two safely today, so no test can see
    # this line go; it is here so that a change in that order cannot turn
    # every second save into a 500.
    session.flush()

    if body.tiers != default_tiers():
        updated_at = datetime.now().isoformat()
        for format_name, rank in tiers_to_ranks(body.tiers).items():
            session.add(
                FormatOrderRow(
                    format=format_name,
                    rank=rank,
                    updated_at=updated_at,
                )
            )

    session.commit()
    return _format_order_state(session)
