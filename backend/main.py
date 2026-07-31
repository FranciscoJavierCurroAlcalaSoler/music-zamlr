import json
import os
from dataclasses import dataclass
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select

from database import get_session
from enums import ActionType, OperationStatus
from importing import OperationResult, PlannedOperation, execute_plan, plan_import
from matching import Match, MatchResult, match_collections
from models import Collection, Track
from schemas import (
    CollectionRead,
    DiffRead,
    ImportPreviewRead,
    ImportRequest,
    ImportResultRead,
    OperationResultRead,
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


def _build_plan(request: ImportRequest, session: Session) -> list[PlannedOperation]:
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
    mine_id = request.mine_collection_id
    theirs_id = request.theirs_collection_id
    track_ids = set(request.track_ids)
    destination_root = request.destination_root

    if not os.path.isdir(destination_root):
        raise HTTPException(
            status_code=400,
            detail="Destination root does not exist or is not a directory.",
        )
    if not os.access(destination_root, os.W_OK):
        raise HTTPException(status_code=400, detail="Destination root is not writable.")

    mine_collection, theirs_collection = _load_collections(session, mine_id, theirs_id)
    match_result = _run_diff(session, mine_collection, theirs_collection)

    missing: list[Track] = []
    upgrade_available: list[Match] = []
    placed_ids: set[int] = set()

    for track in match_result.missing:
        if track.id in track_ids:
            missing.append(track)
            placed_ids.add(track.id)

    for match in match_result.upgrade_available:
        if match.theirs.id in track_ids:
            upgrade_available.append(match)
            placed_ids.add(match.theirs.id)

    rejected_ids = sorted(track_ids - placed_ids)

    if rejected_ids:
        raise HTTPException(
            status_code=400,
            detail=f"Not import candidates (already have, needs review, or the diff changed): {', '.join(str(i) for i in rejected_ids)}",
        )

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

    return import_plan


@dataclass
class PreviewResult:
    operations: list[PlannedOperation]
    operation_counts: dict[str, int]


@app.post("/api/import/preview", response_model=ImportPreviewRead)
def preview_import(
    request: ImportRequest,
    session: Session = Depends(get_session),
):

    import_plan = _build_plan(request, session)

    preview = PreviewResult(
        operations=import_plan,
        operation_counts={
            "copy": sum(1 for op in import_plan if op.action == ActionType.COPY),
            "delete": sum(1 for op in import_plan if op.action == ActionType.DELETE),
            "move": sum(1 for op in import_plan if op.action == ActionType.MOVE),
            "overwrites": sum(1 for op in import_plan if op.overwrites),
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

    operation_results = execute_plan(import_plan)

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
