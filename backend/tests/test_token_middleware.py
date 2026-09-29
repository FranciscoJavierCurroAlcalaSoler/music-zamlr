import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from token_middleware import TokenMiddleware

TOKEN = "known-test-token"


def create_app():
    app = FastAPI()

    @app.get("/")
    async def route():
        return {"message": "ok"}

    # Starlette applies middleware in reverse registration order; this makes
    # CORS outermost, as in main.py, so CORS handles preflight before auth.
    app.add_middleware(TokenMiddleware, secret=TOKEN)
    app.add_middleware(CORSMiddleware, allow_origins=["*"])
    return app


@pytest.fixture
def client():
    # Entered as a context manager, which is what makes TestClient run the
    # lifespan event. That event reaches the middleware as a scope with no
    # headers in it, so this is the only thing here that exercises the
    # pass-through for a scope that is not http. A plain TestClient(app)
    # never sends one, and the pass-through could be deleted unnoticed.
    with TestClient(create_app()) as test_client:
        yield test_client


def test_a_request_without_the_token_is_refused(client):
    response = client.get("/", headers={"Origin": "http://localhost:3000"})

    assert response.status_code == 401
    assert "detail" in response.json()
    assert response.headers["access-control-allow-origin"] == "*"


def test_a_wrong_token_is_refused(client):
    response = client.get("/", headers={"X-Zamlr-Token": "wrong-token"})

    assert response.status_code == 401


def test_the_right_token_passes(client):
    response = client.get("/", headers={"X-Zamlr-Token": TOKEN})

    assert response.status_code == 200


def test_a_non_ascii_token_does_not_raise(client):
    # Sent as raw bytes, because httpx encodes a str header value as ASCII and
    # would refuse this one before it left the client. A real caller is under
    # no such restraint: it writes the byte, and Starlette decodes the header
    # as latin-1, which is how a non-ASCII str reaches the comparison at all.
    response = client.get("/", headers={"X-Zamlr-Token": "ü".encode("latin-1")})

    assert response.status_code == 401


def test_a_preflight_passes_without_the_token(client):
    response = client.options(
        "/",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
