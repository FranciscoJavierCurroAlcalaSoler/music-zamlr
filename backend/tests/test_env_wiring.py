import json
import os
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

import pytest

from launch_settings import (
    ALLOWED_ORIGINS_VARIABLE,
    DATABASE_PATH_VARIABLE,
    FPCALC_PATH_VARIABLE,
    TOKEN_VARIABLE,
)

BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
CHILD_SCRIPT = Path(__file__).with_name("env_wiring_child.py")
TOKEN = "test-token-123"
CONFIGURED_ORIGIN = "http://tauri.localhost"


class ChildRun(NamedTuple):
    """One run of the child, kept apart from what this file asked for.

    answers comes out of the child. database_path is what this file put into
    the environment. Keeping the two in separate fields is what stops a test
    from comparing the child's own output with itself, which proves nothing.
    """

    answers: dict
    database_path: str
    fpcalc_path: str


@pytest.fixture(scope="module")
def child_run(tmp_path_factory):
    """Run main.py once in a child process and return what it answered.

    Module scope because a fresh interpreter has to import FastAPI, SQLModel
    and the whole app, which costs about two seconds. Both tests read this
    one run.
    """
    # A copy, because env= replaces the environment instead of adding to it,
    # and a child on Windows with nothing in its environment cannot start.
    # Every ZAMLR_ name is dropped from the copy, so a variable left set in
    # the terminal that runs pytest cannot change what this test proves.
    environment = {k: v for k, v in os.environ.items() if not k.startswith("ZAMLR_")}
    # A script started by its path gets its own folder as sys.path[0], and
    # this one lives in tests/, so `import main` needs the directory above it.
    environment["PYTHONPATH"] = str(BACKEND_DIRECTORY)
    # The names come from launch_settings, never spelled out here. A name
    # typed by hand and misspelled leaves the variable unset, and every
    # reader then falls back to the behaviour it has without a launcher —
    # which looks like a working test right up to the assertion.
    environment[TOKEN_VARIABLE] = TOKEN
    environment[ALLOWED_ORIGINS_VARIABLE] = CONFIGURED_ORIGIN
    # Under tmp_path_factory, not tmp_path, which has function scope and
    # cannot reach a fixture that runs once for the module. The child creates
    # the tables here, so nothing it does touches backend/db.
    #
    # One level deeper than mktemp goes, because mktemp makes its directory
    # and the packaged app will not: the shell names a folder in app-data
    # that has never existed. Without a missing directory here, nothing in
    # this test would notice create_db_and_tables losing its makedirs call.
    database_path = os.path.normpath(
        str(tmp_path_factory.mktemp("database") / "zamlr" / "test.db")
    )
    environment[DATABASE_PATH_VARIABLE] = database_path
    # An empty file is enough: nothing here runs it, and what is under test
    # is whether fingerprinting.py read the variable at import.
    fpcalc_path = os.path.normpath(str(tmp_path_factory.mktemp("fpcalc") / "fpcalc"))
    Path(fpcalc_path).touch()
    environment[FPCALC_PATH_VARIABLE] = fpcalc_path

    child = subprocess.run(
        [sys.executable, str(CHILD_SCRIPT)],
        env=environment,
        capture_output=True,
        text=True,
        # Explicit, because the default is the machine's code page, which
        # differs between this notebook and the runners in CI.
        encoding="utf-8",
    )
    # stderr in the message: without it, an import error in the child arrives
    # here as a JSON error, which sends you looking at the wrong file.
    assert child.returncode == 0, child.stderr
    # The last line only. Anything that writes to stdout before the answer
    # would otherwise break the parse and look like the same failure.
    answers = json.loads(child.stdout.strip().splitlines()[-1])
    return ChildRun(
        answers=answers, database_path=database_path, fpcalc_path=fpcalc_path
    )


def test_main_reads_the_token_from_the_environment(child_run):
    assert child_run.answers["no_token"] == 401
    assert child_run.answers["with_token"] == 200


def test_main_reads_the_origins_from_the_environment(child_run):
    # Status codes rather than the value of launch_settings, deliberately:
    # reading the settings out of the child would pass against a main.py that
    # reads them correctly and then hands the middleware something else.
    # These two answers can only come from the middleware the file built.
    assert child_run.answers["configured_origin"] == 200
    assert child_run.answers["default_origin"] == 400


def test_the_database_path_comes_from_the_environment(child_run):
    # Two claims, and the second one is not spare. The engine can carry the
    # right path while create_db_and_tables never makes the folder the shell
    # named, and the app would then fail on the first query rather than here.
    assert child_run.answers["engine_database_path"] == child_run.database_path
    assert Path(child_run.database_path).exists()


def test_the_fpcalc_path_comes_from_the_environment(child_run):
    assert child_run.answers["fpcalc_path"] == child_run.fpcalc_path
