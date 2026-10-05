"""Copy the freshly built backend into the folder the desktop shell bundles.

Tauri packs whatever sits in frontend/src-tauri/binaries/ into the installer
and checks nothing about it. A copy made by hand goes stale without a sign:
the tests run against the new backend while the installer carries the old
one. Running this after every PyInstaller build is what keeps the two equal.

Usage, from backend/ after `pyinstaller music-zamlr-backend.spec`:

    python stage_backend.py
"""

import os
import shutil
from pathlib import Path

BACKEND_NAME = "music-zamlr-backend"
# PyInstaller adds .exe on Windows only. The shell looks for the same name.
BACKEND_PROGRAM = BACKEND_NAME + (".exe" if os.name == "nt" else "")
INTERNAL_DIR = "_internal"


def stage_backend(dist_dir: Path, binaries_dir: Path) -> None:
    if not dist_dir.is_dir():
        raise FileNotFoundError(
            f"No backend build at {dist_dir}. "
            "Run `pyinstaller music-zamlr-backend.spec` in backend/ first."
        )

    # Only the backend's own files go. fpcalc shares this folder and
    # nothing rebuilds it, so emptying the folder would ship an app that
    # falls back to tags on every comparison.
    (binaries_dir / BACKEND_PROGRAM).unlink(missing_ok=True)
    old_internal = binaries_dir / INTERNAL_DIR
    if old_internal.exists():
        shutil.rmtree(old_internal)

    # Deleted first rather than copied over with dirs_exist_ok=True, which
    # replaces the files both builds have and keeps every file only the old
    # one had. A module removed from the backend would ride along in every
    # installer after it.
    binaries_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(dist_dir / BACKEND_PROGRAM, binaries_dir / BACKEND_PROGRAM)
    shutil.copytree(dist_dir / INTERNAL_DIR, binaries_dir / INTERNAL_DIR)


def main() -> None:
    # Anchored to this file, not the working directory, so the script finds
    # both folders whichever directory it is started from.
    backend_dir = Path(__file__).resolve().parent
    stage_backend(
        dist_dir=backend_dir / "dist" / BACKEND_NAME,
        binaries_dir=backend_dir.parent / "frontend" / "src-tauri" / "binaries",
    )


if __name__ == "__main__":
    main()
