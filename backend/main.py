import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from database import create_collection, get_session
from enums import ActionType, Bucket, OperationStatus
from importing import OperationResult, PlannedOperation, execute_plan, plan_import
from matching import Match, MatchResult, classify_pairing, match_collections
from models import Collection, Track
from scanner import ScanProgress, scan_folder
from schemas import (
    CollectionRead,
    DiffRead,
    ImportPreviewRead,
    ImportRequest,
    ImportResultRead,
    OperationResultRead,
    ScanProgressRead,
    ScanRequest,
    ScanResultRead,
    TrackRead,
)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/tracks", response_model=list[TrackRead])
def list_tracks(session: Session = Depends(get_session)):
    return session.exec(select(Track)).all()


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
    session: Session, mine_collection: Collection, theirs_collection: Collection
) -> MatchResult:
    tracks_mine = session.exec(
        select(Track).where(Track.collection_id == mine_collection.id)
    ).all()
    tracks_theirs = session.exec(
        select(Track).where(Track.collection_id == theirs_collection.id)
    ).all()
    match_result = match_collections(tracks_mine, tracks_theirs)
    session.commit()  # persist the hashes the matcher computed
    return match_result


@app.get("/api/diff", response_model=DiffRead)
def diff_collections(
    mine: int,
    theirs: int,
    session: Session = Depends(get_session),
):
    mine_collection, theirs_collection = _load_collections(session, mine, theirs)
    match_result = _run_diff(session, mine_collection, theirs_collection)

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

    return diff_result


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


def _build_plan(request: ImportRequest, session: Session) -> BuiltPlan:
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

    if not os.path.isdir(destination_root):
        raise HTTPException(
            status_code=400,
            detail="Destination root does not exist or is not a directory.",
        )
    if not os.access(destination_root, os.W_OK):
        raise HTTPException(status_code=400, detail="Destination root is not writable.")

    mine_collection, theirs_collection = _load_collections(
        session, mine_collection_id, theirs_collection_id
    )
    match_result = _run_diff(session, mine_collection, theirs_collection)

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
                pairing_bucket = classify_pairing(mine_track=mine, theirs_track=theirs)
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

    return BuiltPlan(operations=import_plan, upgrades=upgrade_available)


@dataclass
class PreviewResult:
    operations: list[PlannedOperation]
    upgrades: list[Match]
    operation_counts: dict[str, int]


@app.post("/api/import/preview", response_model=ImportPreviewRead)
def preview_import(
    request: ImportRequest,
    session: Session = Depends(get_session),
):

    import_plan = _build_plan(request, session)

    preview = PreviewResult(
        operations=import_plan.operations,
        upgrades=import_plan.upgrades,
        operation_counts={
            "copy": sum(
                1 for op in import_plan.operations if op.action == ActionType.COPY
            ),
            "delete": sum(
                1 for op in import_plan.operations if op.action == ActionType.DELETE
            ),
            "move": sum(
                1 for op in import_plan.operations if op.action == ActionType.MOVE
            ),
            "overwrites": sum(1 for op in import_plan.operations if op.overwrites),
        },
    )

    return preview


@dataclass
class ImportResult:
    operations: list[OperationResult]
    status_counts: dict[str, int]
    log_path: str | None = None
    log_error: str | None = None


def _write_import_log(
    destination_root: str, results: list[OperationResult]
) -> tuple[str | None, str | None]:
    log_path = None
    log_error = None
    candidate_path = os.path.normpath(
        os.path.join(
            destination_root,
            "import_log_" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".json",
        )
    )
    try:
        log_entries = [
            OperationResultRead.model_validate(r).model_dump(mode="json")
            for r in results
        ]
        with open(candidate_path, "w", encoding="utf-8") as log_file:
            json.dump(log_entries, log_file, indent=2, ensure_ascii=False)
        log_path = candidate_path
    except OSError as error:
        log_error = str(error)

    return log_path, log_error


@app.post("/api/import/execute", response_model=ImportResultRead)
def execute_import(
    request: ImportRequest,
    session: Session = Depends(get_session),
):

    import_plan = _build_plan(request, session)

    operation_results = execute_plan(import_plan.operations)

    # Successful deletes and moves leave rows pointing at files that no
    # longer exist; the next diff would offer the same upgrade again and
    # then fail on the delete. Copies deliberately get no rows: the
    # destination root is any folder the user picked, so nothing guarantees
    # it sits inside mine's collection tree. A re-scan is how they appear.
    for result in operation_results:
        if result.status == OperationStatus.SUCCESS and result.operation.action in (
            ActionType.DELETE,
            ActionType.MOVE,
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
                1 for r in operation_results if r.status == OperationStatus.SUCCESS
            ),
            "failed": sum(
                1 for r in operation_results if r.status == OperationStatus.FAILED
            ),
            "skipped": sum(
                1 for r in operation_results if r.status == OperationStatus.SKIPPED
            ),
        },
        log_path=log_path,
        log_error=log_error,
    )

    return import_result


PROGRESS_INTERVAL_SECONDS = 0.2


def _sse(event: str, payload: dict) -> str:
    """One Server-Sent Events frame: an event line, a data line, a blank line.

    json.dumps escapes every newline inside a string, so no payload can split
    a frame in two. That is why a single data: line is always enough here.
    """
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


def _scan_stream(root_path: str, collection_id: int, engine) -> StreamingResponse:
    """Scan on a worker thread and stream the progress as Server-Sent Events.

    Both scan endpoints end in a call to this, so the two cannot drift apart.

    Every parameter is a plain value on purpose. The request's Session belongs
    to the request's thread, and neither it nor anything it loaded may cross
    into the worker; the engine is the one database object that is safe to
    share, because it owns the pool and the Session is what is not thread-safe.
    """
    latest: ScanProgress | None = None

    def remember(progress: ScanProgress) -> None:
        # One rebinding per call, so the reader below always sees a whole
        # ScanProgress and never a half-written one. Progress is a state
        # rather than a log: only the newest value has any use, so this
        # overwrites instead of collecting a backlog that nobody reads and
        # that would hold one object per file for the length of the scan.
        nonlocal latest
        latest = progress

    def run_scan() -> tuple[str, dict]:
        """Do the scan and build the final frame. Runs on a worker thread.

        The payload is built in here, while the session is still open.
        ScanResult.collection is an ORM object, and serializing it after its
        session closes raises DetachedInstanceError.

        Every exception is caught, which the project's convention normally
        forbids. It has to be: StreamingResponse has already sent 200 by the
        time this runs, so a failure has nowhere to go except the stream
        itself. The traceback still reaches the server log, so a bug stays as
        loud as it was, only in a different place.
        """
        try:
            with Session(engine) as session:
                result = scan_folder(
                    root_path, collection_id, session, on_progress=remember
                )
                payload = ScanResultRead.model_validate(result).model_dump(mode="json")
            return "done", payload
        except Exception as error:
            logging.exception("Scan of %s failed", root_path)
            return "error", {"detail": str(error)}

    async def frames():
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(None, run_scan)
        while not future.done():
            # This sleep is what hands control back to the event loop, so the
            # server still answers other requests while a drive is read.
            await asyncio.sleep(PROGRESS_INTERVAL_SECONDS)
            progress = latest
            # None until the scanner's first report lands, and a fast scan can
            # finish before any of them arrive, so a stream with no progress
            # frame at all is normal rather than a fault.
            if progress is not None:
                yield _sse(
                    "progress",
                    ScanProgressRead.model_validate(progress).model_dump(mode="json"),
                )
        # run_scan catches its own failures, so this never re-raises. That
        # also means a client that disconnects mid-scan leaves no exception
        # sitting unretrieved on the future.
        event, payload = future.result()
        yield _sse(event, payload)

    return StreamingResponse(
        frames(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
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

    return _scan_stream(collection.root_path, collection.id, session.get_bind())


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

    return _scan_stream(collection.root_path, collection.id, session.get_bind())
