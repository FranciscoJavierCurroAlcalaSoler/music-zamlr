
from fastapi import FastAPI, Depends, HTTPException
from sqlmodel import Session, select
from dataclasses import dataclass

from fastapi.middleware.cors import CORSMiddleware

from database import get_session
from models import Track, Collection
from schemas import TrackRead, CollectionRead, DiffRead
from matching import match_collections, MatchResult

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
        raise HTTPException(status_code=400, detail="Cannot diff a collection against itself.")

    mine_collection = session.get(Collection, mine)
    theirs_collection = session.get(Collection, theirs)
    if mine_collection is None or theirs_collection is None:
        raise HTTPException(status_code=404, detail="Collection not found.")

    tracks_mine = session.exec(
        select(Track).where(Track.collection_id == mine)
    ).all()
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
            only_in_mine=len(result.only_in_mine)
        )
    )
    
    return diff