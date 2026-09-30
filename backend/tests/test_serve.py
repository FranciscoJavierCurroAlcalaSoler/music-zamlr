import logging
import os
import subprocess
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import NamedTuple

import httpx
import pytest

from launch_settings import (
    DATABASE_PATH_VARIABLE,
    LOG_DIRECTORY_VARIABLE,
    TOKEN_VARIABLE,
)
from serve import (
    LOG_FILE_NAME,
    LOG_LINE_PREFIX,
    PORT_LINE_PREFIX,
    bind_local_socket,
    configure_file_logging,
    port_line,
)

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


class ServerRun(NamedTuple):
    """One real server, with the paths this file configured for it."""

    port: int
    database_path: Path
    log_path: Path
    announced_log: str


@pytest.fixture
def restore_root_logger():
    """Put the root logger back as it was, whatever a test did to it.

    A handler left attached writes into a temporary directory that pytest is
    about to delete, and on Windows it also keeps that file open. The level
    is restored too, because the file logging raises it to INFO.
    """
    root_logger = logging.getLogger()
    handlers = list(root_logger.handlers)
    level = root_logger.level
    yield
    for handler in root_logger.handlers:
        if handler not in handlers:
            handler.close()
    root_logger.handlers = handlers
    root_logger.setLevel(level)


@pytest.fixture(scope="module")
def running_server(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("running-server")
    environment = {k: v for k, v in os.environ.items() if not k.startswith("ZAMLR_")}
    environment[TOKEN_VARIABLE] = TOKEN
    # Or the real server writes into backend/db: the lifespan runs here, and
    # it calls create_db_and_tables.
    database_path = tmp_path / "serve-test.db"
    # A directory. The file inside it is the application's to name, which is
    # why the test reads that name from serve.py instead of choosing one.
    log_directory = tmp_path / "logs"
    log_path = log_directory / LOG_FILE_NAME
    environment[DATABASE_PATH_VARIABLE] = str(database_path)
    environment[LOG_DIRECTORY_VARIABLE] = str(log_directory)

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
        port, announced_log = _read_announcements(process)

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
        yield ServerRun(
            port=port,
            database_path=database_path,
            log_path=log_path,
            announced_log=announced_log,
        )
    finally:
        killer.cancel()
        process.terminate()
        process.wait(timeout=START_TIMEOUT_SECONDS)


def test_the_server_answers_on_the_port_it_announced(running_server):
    assert running_server.port > 0
    assert running_server.database_path.exists()


def test_the_log_file_is_written(running_server):
    assert running_server.log_path.exists()
    # The port, because that line is written at INFO. The root logger starts
    # at WARNING and a handler never sees a record its logger rejected, so
    # this assertion is what catches a file that holds errors alone.
    assert str(running_server.port) in running_server.log_path.read_text(
        encoding="utf-8"
    )


def test_the_announced_log_path_is_the_file_that_was_written(running_server):
    # The shell shows the user this path. If it names a file that nothing
    # writes to, the log opens empty and the fault looks like the app's.
    assert running_server.announced_log == str(running_server.log_path)


def test_the_file_is_the_only_handler_left(tmp_path, restore_root_logger):
    # Stated here rather than left to the process it runs in. scanner.py
    # calls basicConfig at import, so a console handler and an INFO root
    # level both arrive by accident; these two assertions are what make the
    # function answerable for them.
    root_logger = logging.getLogger()
    # Put back to the level a fresh interpreter starts at. Without this the
    # assertion below reads scanner.py's basicConfig, not this function, and
    # passes with the level line deleted.
    root_logger.setLevel(logging.WARNING)

    configure_file_logging(str(tmp_path / "logs"))

    assert [type(h) for h in root_logger.handlers] == [RotatingFileHandler]
    assert root_logger.level == logging.INFO


def test_a_non_ascii_path_reaches_the_log(tmp_path, restore_root_logger):
    # A directory named in Japanese, holding a record naming a Japanese
    # path. On Linux and macOS this passes either way, because their default
    # encoding is already UTF-8. It earns its place on Windows, where the
    # default is the machine's code page and this raises inside logging.
    log_directory = tmp_path / "日志"
    message = "café — 東京"

    log_path = Path(configure_file_logging(str(log_directory)))
    logging.getLogger().error(message)
    for handler in logging.getLogger().handlers:
        handler.flush()

    assert message in log_path.read_text(encoding="utf-8")


def _read_announcements(process: subprocess.Popen) -> tuple[int, str]:
    """Read lines until both announcements, and report the rest on failure.

    Uvicorn writes its own startup lines, so each announcement is found by
    its prefix rather than by its position. Everything read on the way is
    kept for the failure message, which is the only place a child's own
    traceback appears.
    """
    seen = []
    port = None
    log_path = None
    for line in process.stdout:
        if line.startswith(PORT_LINE_PREFIX):
            port = int(line.removeprefix(PORT_LINE_PREFIX).strip())
        elif line.startswith(LOG_LINE_PREFIX):
            log_path = line.removeprefix(LOG_LINE_PREFIX).strip()
        else:
            seen.append(line)
        if port is not None and log_path is not None:
            return port, log_path
    raise AssertionError(
        f"The server announced port={port} and log={log_path}. Its output was:\n"
        + "".join(seen)
    )
