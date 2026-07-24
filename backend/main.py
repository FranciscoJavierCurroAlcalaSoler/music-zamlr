import os
from dataclasses import dataclass

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select

from database import get_session
from enums import ActionType
from importing import PlannedOperation, plan_import
from matching import Match, MatchResult, match_collections
from models import Collection, Track
from schemas import (
    CollectionRead,
    DiffRead,
    ImportPreviewRead,
    ImportRequest,
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


@app.get("/api/diff", response_model=DiffRead)
def diff_collections(
    mine: int,
    theirs: int,
    session: Session = Depends(get_session),
):
    if mine == theirs:
        raise HTTPException(
            status_code=400, detail="Cannot diff a collection against itself."
        )

    mine_collection = session.get(Collection, mine)
    theirs_collection = session.get(Collection, theirs)
    if mine_collection is None or theirs_collection is None:
        raise HTTPException(status_code=404, detail="Collection not found.")

    tracks_mine = session.exec(select(Track).where(Track.collection_id == mine)).all()
    tracks_theirs = session.exec(
        select(Track).where(Track.collection_id == theirs)
    ).all()

    result = match_collections(tracks_mine, tracks_theirs)

    # persist the hashes the matcher computed
    session.commit()

    diff = DiffResult(
        match_results=result,
        match_counts=dict(
            missing=len(result.missing),
            upgrade_available=len(result.upgrade_available),
            already_have=len(result.already_have),
            needs_review=len(result.needs_review),
            only_in_mine=len(result.only_in_mine),
        ),
    )

    return diff


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
    mine = request.mine_collection_id
    theirs = request.theirs_collection_id
    track_ids = set(request.track_ids)

    if mine == theirs:
        raise HTTPException(
            status_code=400, detail="Cannot import from own collection."
        )

    destination_root = request.destination_root

    if not os.path.isdir(destination_root):
        raise HTTPException(
            status_code=400,
            detail="Destination root does not exist or is not a directory.",
        )
    if not os.access(destination_root, os.W_OK):
        raise HTTPException(status_code=400, detail="Destination root is not writable.")

    mine_collection = session.get(Collection, mine)
    theirs_collection = session.get(Collection, theirs)
    if mine_collection is None or theirs_collection is None:
        raise HTTPException(status_code=404, detail="Collection not found.")

    tracks_mine = session.exec(select(Track).where(Track.collection_id == mine)).all()
    tracks_theirs = session.exec(
        select(Track).where(Track.collection_id == theirs)
    ).all()

    result = match_collections(tracks_mine, tracks_theirs)

    # persist the hashes the matcher computed
    session.commit()

    missing: list[Track] = []
    upgrade_available: list[Match] = []
    placed_ids: set[int] = set()
    rejected_ids: list[int] = []

    for track in result.missing:
        if track.id in track_ids:
            missing.append(track)
            placed_ids.add(track.id)

    for match in result.upgrade_available:
        if match.theirs.id in track_ids:
            upgrade_available.append(match)
            placed_ids.add(match.theirs.id)

    rejected_ids = sorted(track_ids - placed_ids)

    if len(rejected_ids) > 0:
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
