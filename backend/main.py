from fastapi import FastAPI, Depends
from sqlmodel import Session, select

from fastapi.middleware.cors import CORSMiddleware

from database import engine
from models import Track
from schemas import TrackRead

def get_session():
    with Session(engine) as session:
        yield session

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
