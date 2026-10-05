"""The built binary, exercised as the shell will run it.

Everything else in the suite tests the source. This file tests the bundle,
which is a different artifact: a hidden import that PyInstaller could not
follow is invisible until something runs the collected program.

The whole file is skipped where no build exists, which is every run in CI,
because dist/ is not in the repository.
"""

import subprocess
import threading
import time
from pathlib import Path

import httpx
import pytest

from launch_settings import (
    DATABASE_PATH_VARIABLE,
    FPCALC_PATH_VARIABLE,
    TOKEN_VARIABLE,
    WATCH_STDIN_VARIABLE,
)
from stage_backend import BACKEND_NAME, BACKEND_PROGRAM

BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
BINARY = BACKEND_DIRECTORY / "dist" / BACKEND_NAME / BACKEND_PROGRAM
TOKEN = "packaged-token"
START_TIMEOUT_SECONDS = 30
# Shorter than the guard above, so that the guard cannot answer for an
# assertion: a killer armed for the same count ends the process exactly as
# the wait gives up, and the wait then reports an exit that never happened.
EXIT_TIMEOUT_SECONDS = 10
# A bundle has only to beat the two seconds the source takes to import
# FastAPI, SQLModel and the app, with room for a slow machine. This number
# catches a change of packaging mode, not a slow afternoon.
START_BUDGET_SECONDS = 10

pytestmark = pytest.mark.skipif(
    not BINARY.exists(), reason="the packaged backend is not built"
)


def binary_is_older_than_the_source() -> bool:
    newest_source = max(path.stat().st_mtime for path in BACKEND_DIRECTORY.glob("*.py"))
    return BINARY.stat().st_mtime < newest_source


@pytest.fixture(autouse=True)
def a_current_build():
    # A fail, not a skip. No build at all is a fair reason to say nothing,
    # which the module-level skip already handles. A build that is older than
    # the code is the one way this file can lie: every test passes, against a
    # program nobody is shipping.
    if binary_is_older_than_the_source():
        pytest.fail(
            "The packaged backend is older than the source. "
            "Rebuild it with: pyinstaller music-zamlr-backend.spec"
        )


def start_binary(launch_environment, **variables) -> subprocess.Popen:
    return subprocess.Popen(
        [str(BINARY)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        # Explicit, because the default is the machine's code page and this
        # output crosses a pipe rather than a console.
        encoding="utf-8",
        env=launch_environment(**variables),
    )


def test_the_packaged_backend_answers_on_its_port(
    tmp_path, launch_environment, read_port_line
):
    process = start_binary(
        launch_environment,
        **{
            DATABASE_PATH_VARIABLE: str(tmp_path / "packaged.db"),
            TOKEN_VARIABLE: TOKEN,
            WATCH_STDIN_VARIABLE: "1",
        },
    )
    killer = threading.Timer(START_TIMEOUT_SECONDS, process.kill)
    killer.start()
    try:
        port = read_port_line(process)
        killer.cancel()

        response = httpx.get(
            f"http://127.0.0.1:{port}/api/health",
            headers={"X-Zamlr-Token": TOKEN},
        )

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

        # The exit as well as the answer. Closing the pipe is the only thing
        # that stops this process when the shell dies, and the watcher thread
        # has never run inside a bundle before.
        process.stdin.close()
        process.wait(timeout=EXIT_TIMEOUT_SECONDS)
    finally:
        killer.cancel()
        process.kill()
        process.wait(timeout=EXIT_TIMEOUT_SECONDS)


def test_the_packaged_backend_refuses_without_a_database_path(launch_environment):
    # The only test of sys.frozen being true. The unit tests cover the
    # predicate; nothing but a real bundle sets the flag it reads. Without
    # the refusal, a binary started by hand writes its catalog into the
    # install folder, which an update replaces.
    process = start_binary(launch_environment)

    output, _ = process.communicate(timeout=START_TIMEOUT_SECONDS)

    assert process.returncode != 0
    assert DATABASE_PATH_VARIABLE in output


def test_the_packaged_backend_starts_within_the_budget(
    tmp_path, launch_environment, read_port_line
):
    process = start_binary(
        launch_environment,
        **{DATABASE_PATH_VARIABLE: str(tmp_path / "budget.db")},
    )
    killer = threading.Timer(START_TIMEOUT_SECONDS, process.kill)
    killer.start()
    try:
        started = time.monotonic()
        read_port_line(process)
        elapsed = time.monotonic() - started
    finally:
        killer.cancel()
        process.kill()
        process.wait(timeout=EXIT_TIMEOUT_SECONDS)

    print(f"\npackaged backend announced its port after {elapsed:.2f}s")
    assert elapsed < START_BUDGET_SECONDS


def test_the_packaged_backend_accepts_a_configured_fpcalc(
    tmp_path, launch_environment, read_port_line
):
    # The shell points this at the copy it ships. The assertion is that the
    # process starts and serves at all: fingerprinting.py reads the variable
    # when it is imported, so a value it rejects stops the binary before it
    # can announce a port, and the failure would arrive as a window that
    # never leaves its splash.
    #
    # An empty file is enough, because nothing here runs it. Whether fpcalc
    # truly fingerprints inside the bundle is test_fpcalc_reads_a_real_file's
    # question, and it needs real audio and the real program.
    fpcalc = tmp_path / "fpcalc.exe"
    fpcalc.touch()
    process = start_binary(
        launch_environment,
        **{
            DATABASE_PATH_VARIABLE: str(tmp_path / "fpcalc-test.db"),
            FPCALC_PATH_VARIABLE: str(fpcalc),
        },
    )
    killer = threading.Timer(START_TIMEOUT_SECONDS, process.kill)
    killer.start()
    try:
        port = read_port_line(process)
        killer.cancel()

        response = httpx.get(f"http://127.0.0.1:{port}/api/health")

        assert response.status_code == 200
    finally:
        killer.cancel()
        process.kill()
        process.wait(timeout=EXIT_TIMEOUT_SECONDS)
