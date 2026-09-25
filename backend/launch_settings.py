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

from collections.abc import Mapping
from dataclasses import dataclass

ALLOWED_ORIGINS_VARIABLE = "ZAMLR_ALLOWED_ORIGINS"
DEFAULT_ALLOWED_ORIGINS = ("http://localhost:5173",)


@dataclass(frozen=True)
class LaunchSettings:
    allowed_origins: tuple[str, ...]


def read_launch_settings(environ: Mapping[str, str]) -> LaunchSettings:
    # An absent variable and an empty one are different answers. Absent means
    # nobody launched us, so the browser on the other side is the Vite dev
    # server. Empty means a launcher built its argument and got it wrong,
    # which the loop below refuses rather than reads as "no origins".
    if ALLOWED_ORIGINS_VARIABLE not in environ:
        return LaunchSettings(allowed_origins=DEFAULT_ALLOWED_ORIGINS)

    configured_origins = environ[ALLOWED_ORIGINS_VARIABLE]
    allowed_origins = []
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

    return LaunchSettings(allowed_origins=tuple(allowed_origins))
