"""What the launcher tells the backend, read out of its environment.

Nothing from this project is imported here, so any module can read these
settings. database.py needs them and is itself imported by main.py, so
settings that lived in main.py would close that loop into an import cycle.
enums.py sits below everything for the same reason.

The environment arrives as a parameter instead of being read from os.environ
here, which is what lets a test pass a plain dict rather than change the
environment of the whole pytest process. It is the same rule the planner
follows with path_exists.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass

ALLOWED_ORIGINS_VARIABLE = "ZAMLR_ALLOWED_ORIGINS"
TOKEN_VARIABLE = "ZAMLR_TOKEN"
DATABASE_PATH_VARIABLE = "ZAMLR_DATABASE_PATH"
FPCALC_PATH_VARIABLE = "ZAMLR_FPCALC"
LOG_DIRECTORY_VARIABLE = "ZAMLR_LOG_DIR"
DEFAULT_ALLOWED_ORIGINS = ("http://localhost:5173",)


@dataclass(frozen=True)
class LaunchSettings:
    allowed_origins: tuple[str, ...]
    token: str | None
    database_path: str | None
    fpcalc_path: str | None
    log_directory: str | None


def read_launch_settings(environ: Mapping[str, str]) -> LaunchSettings:
    allowed_origins = []
    token = None
    database_path = None
    fpcalc_path = None
    log_directory = None

    # An absent variable and an empty one are different answers. Absent means
    # nobody launched us, so the browser on the other side is the Vite dev
    # server. Empty means a launcher built its argument and got it wrong,
    # which the loop below refuses rather than reads as "no origins".
    if ALLOWED_ORIGINS_VARIABLE not in environ:
        allowed_origins = DEFAULT_ALLOWED_ORIGINS
    else:
        configured_origins = environ[ALLOWED_ORIGINS_VARIABLE]
        # Every refusal below is loud on purpose. CORSMiddleware compares whole
        # strings against the Origin header, which carries no path, so an empty
        # entry or a trailing slash matches nothing and the browser blocks the
        # frontend. The frontend cannot tell that apart from a server that never
        # answered: both arrive at fetch() as a TypeError, and describeFetchError
        # then asks whether the backend is running while it is running perfectly.
        # Raising here names the real cause at the only moment it is still visible.
        for raw_origin in configured_origins.split(","):
            origin = raw_origin.strip()
            if not origin:
                raise ValueError(
                    f"{ALLOWED_ORIGINS_VARIABLE} contains an empty origin entry"
                )
            # A wildcard is refused rather than passed through: it would let any
            # page the browser happens to have open call this server, and the
            # import endpoint deletes files on the user's disk.
            if origin == "*":
                raise ValueError(f"{ALLOWED_ORIGINS_VARIABLE} must not contain '*'")
            if origin.endswith("/"):
                raise ValueError(
                    f"{ALLOWED_ORIGINS_VARIABLE} origin must not end with '/': {origin}"
                )
            allowed_origins.append(origin)

    if TOKEN_VARIABLE in environ:
        token = environ[TOKEN_VARIABLE].strip()
        if not token:
            raise ValueError(f"{TOKEN_VARIABLE} contains an empty token")

    if DATABASE_PATH_VARIABLE in environ:
        db_path = environ[DATABASE_PATH_VARIABLE].strip()
        if not db_path:
            raise ValueError(f"{DATABASE_PATH_VARIABLE} contains an empty path")
        # Refused before the directory is worked out, because a relative path
        # resolves against a working directory the shell chooses, and SQLite
        # answers a path that points nowhere useful by making an empty file
        # there and reporting nothing. The catalog then looks lost.
        if not os.path.isabs(db_path):
            raise ValueError(f"{DATABASE_PATH_VARIABLE} must be an absolute path")
        database_path = os.path.normpath(db_path)

    if FPCALC_PATH_VARIABLE in environ:
        fpcalc_path = environ[FPCALC_PATH_VARIABLE].strip()
        if not fpcalc_path:
            raise ValueError(f"{FPCALC_PATH_VARIABLE} contains an empty path")
        if not os.path.isabs(fpcalc_path):
            raise ValueError(f"{FPCALC_PATH_VARIABLE} must be an absolute path")
        fpcalc_path = os.path.normpath(fpcalc_path)

    if LOG_DIRECTORY_VARIABLE in environ:
        log_directory = environ[LOG_DIRECTORY_VARIABLE].strip()
        if not log_directory:
            raise ValueError(f"{LOG_DIRECTORY_VARIABLE} contains an empty path")
        if not os.path.isabs(log_directory):
            raise ValueError(f"{LOG_DIRECTORY_VARIABLE} must be an absolute path")
        log_directory = os.path.normpath(log_directory)

    return LaunchSettings(
        allowed_origins=tuple(allowed_origins),
        token=token,
        database_path=database_path,
        fpcalc_path=fpcalc_path,
        log_directory=log_directory,
    )
