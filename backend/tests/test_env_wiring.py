import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
CHILD_SCRIPT = Path(__file__).with_name("env_wiring_child.py")
TOKEN = "test-token-123"
CONFIGURED_ORIGIN = "http://tauri.localhost"


@pytest.fixture(scope="module")
def child_results():
    """Run main.py once in a child process and return the four answers.

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
    environment["ZAMLR_TOKEN"] = TOKEN
    environment["ZAMLR_ALLOWED_ORIGINS"] = CONFIGURED_ORIGIN

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
    return json.loads(child.stdout.strip().splitlines()[-1])


def test_main_reads_the_token_from_the_environment(child_results):
    assert child_results["no_token"] == 401
    assert child_results["with_token"] == 200


def test_main_reads_the_origins_from_the_environment(child_results):
    # Status codes rather than the value of launch_settings, deliberately:
    # reading the settings out of the child would pass against a main.py that
    # reads them correctly and then hands the middleware something else.
    # These two answers can only come from the middleware the file built.
    assert child_results["configured_origin"] == 200
    assert child_results["default_origin"] == 400
