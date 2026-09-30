import os
import subprocess
import sys
import threading
from pathlib import Path

import httpx

from launch_settings import DATABASE_PATH_VARIABLE, TOKEN_VARIABLE
from serve import PORT_LINE_PREFIX, bind_local_socket, port_line

SERVE_SCRIPT = Path(__file__).resolve().parents[1] / "serve.py"
TOKEN = "serve-test-token"
# Long enough for a cold interpreter to import FastAPI, SQLModel and the app,
# which takes about two seconds here. It is a guard against a hang, not a
# measurement of how fast the start is, and it is also what a failing run
# costs, so it stays as short as that leaves it safe.
START_TIMEOUT_SECONDS = 15


def test_the_port_line_carries_the_port():
    # The literal, not an f-string over PORT_LINE_PREFIX, which would agree
    # with whatever the prefix became. The shell parses this exact text.
    assert port_line(12345) == "ZAMLR_PORT=12345"


def test_the_socket_listens_on_the_loopback_address():
    server_socket = bind_local_socket()
    try:
        address, port = server_socket.getsockname()

        assert address == "127.0.0.1"
        assert port > 0
    finally:
        # Closed here, or every run of the suite leaves a listening socket
        # behind until the interpreter exits.
        server_socket.close()


def test_two_sockets_get_different_ports():
    # Port 0 is what this asserts, without naming it. A fixed port works
    # perfectly in a test that opens one socket, and collides the moment
    # anything else holds it — a development backend, or a second copy of
    # the app. Two at once is the cheapest way to see the difference.
    first = bind_local_socket()
    second = bind_local_socket()
    try:
        assert first.getsockname()[1] != second.getsockname()[1]
    finally:
        first.close()
        second.close()


def test_the_server_answers_on_the_port_it_announced(tmp_path):
    environment = {k: v for k, v in os.environ.items() if not k.startswith("ZAMLR_")}
    environment[TOKEN_VARIABLE] = TOKEN
    # Or the real server writes into backend/db: the lifespan runs here, and
    # it calls create_db_and_tables.
    database_path = tmp_path / "serve-test.db"
    environment[DATABASE_PATH_VARIABLE] = str(database_path)

    process = subprocess.Popen(
        [sys.executable, str(SERVE_SCRIPT)],
        stdout=subprocess.PIPE,
        # Merged, so that a child that dies on import reports why through the
        # same pipe. Read separately, a full stderr could also block a child
        # that nobody is draining.
        stderr=subprocess.STDOUT,
        text=True,
        env=environment,
    )
    # Armed before the first read. readline on a pipe blocks for as long as
    # the child lives, so without this a backend that never announces its
    # port hangs the whole suite instead of failing it. Killing the child
    # closes the pipe, the read returns an empty string, and the loop ends.
    killer = threading.Timer(START_TIMEOUT_SECONDS, process.kill)
    killer.start()
    try:
        port = _read_announced_port(process)

        response = httpx.get(
            f"http://127.0.0.1:{port}/api/health",
            headers={"X-Zamlr-Token": TOKEN},
        )

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        # The lifespan makes this file, so its presence is what proves the
        # server ran against the database this test named. Without the
        # assertion, dropping the variable above still passes here and the
        # run quietly writes into the developer's own catalog instead.
        assert database_path.exists()
    finally:
        killer.cancel()
        process.terminate()
        process.wait(timeout=START_TIMEOUT_SECONDS)


def _read_announced_port(process: subprocess.Popen) -> int:
    """Read lines until the announcement, and report the rest on failure.

    Uvicorn writes its own startup lines, so the announcement is found by its
    prefix rather than by being first. Everything read on the way is kept for
    the failure message, which is the only place a child's traceback appears.
    """
    seen = []
    for line in process.stdout:
        if line.startswith(PORT_LINE_PREFIX):
            return int(line.removeprefix(PORT_LINE_PREFIX).strip())
        seen.append(line)
    raise AssertionError(
        "The server never announced a port. Its output was:\n" + "".join(seen)
    )
