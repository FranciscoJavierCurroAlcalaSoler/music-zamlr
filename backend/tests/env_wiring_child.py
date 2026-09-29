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
from launch_settings import ALLOWED_ORIGINS_VARIABLE, TOKEN_VARIABLE

DEFAULT_ORIGIN = "http://localhost:5173"


def main_child():
    # Both values come from the environment rather than from constants here,
    # so this file cannot drift out of step with whatever the parent chose.
    token = os.environ[TOKEN_VARIABLE]
    origin = os.environ[ALLOWED_ORIGINS_VARIABLE]

    # Not `with TestClient(...)`: the context manager runs the lifespan, which
    # calls create_db_and_tables() and would write into the real backend/db.
    # A middleware is built for the first request, so none of this needs it.
    client = TestClient(main.app)

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
            }
        )
    )


if __name__ == "__main__":
    main_child()
