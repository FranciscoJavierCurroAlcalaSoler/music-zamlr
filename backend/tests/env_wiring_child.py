"""Exercise main.py in a process whose environment the parent test chose.

Not named test_*, so pytest never collects it. It is run by
test_env_wiring.py through subprocess, because pytest imports main.py once,
before any fixture can set a variable, and so can never see main.py read one.

The answers travel back as a single line of JSON on stdout.
"""

import json
import os

from fastapi.testclient import TestClient

import main
from database import apply_migrations, engine
from fingerprinting import _find_fpcalc
from launch_settings import (
    ALLOWED_ORIGINS_VARIABLE,
    DATABASE_PATH_VARIABLE,
    TOKEN_VARIABLE,
)

DEFAULT_ORIGIN = "http://localhost:5173"


def main_child():
    # Both values come from the environment rather than from constants here,
    # so this file cannot drift out of step with whatever the parent chose.
    token = os.environ[TOKEN_VARIABLE]
    origin = os.environ[ALLOWED_ORIGINS_VARIABLE]
    # .get, not [], so the guard below is a real guard: run without the
    # variable, this file must not reach apply_migrations() and write into
    # the developer's own database.
    database_path = os.environ.get(DATABASE_PATH_VARIABLE)

    # Not `with TestClient(...)`: the context manager runs the lifespan, which
    # calls apply_migrations() and would write into the real backend/db. A
    # middleware is built for the first request, so none of this needs it.
    client = TestClient(main.app)

    if database_path:
        apply_migrations()

    no_token = client.get("/api/health")
    with_token = client.get("/api/health", headers={"X-Zamlr-Token": token})
    configured_origin = client.options(
        "/api/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )
    # The default origin has to be refused here. It is what separates "the
    # variable was read" from "the variable was added to the default list".
    default_origin = client.options(
        "/api/health",
        headers={
            "Origin": DEFAULT_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )

    print(
        json.dumps(
            {
                "no_token": no_token.status_code,
                "with_token": with_token.status_code,
                "configured_origin": configured_origin.status_code,
                "default_origin": default_origin.status_code,
                # The engine's own path, read back from the engine database.py
                # built. The parent compares it with the path it set, so the
                # expected value never travels through this file.
                "engine_database_path": engine.url.database,
                "fpcalc_path": _find_fpcalc(),
            }
        )
    )


if __name__ == "__main__":
    main_child()
