"""Write the licence notices for everything a release installs.

One file, installed beside the program and attached to the release, holding
every licence text the installer's contents oblige it to carry: the project's
own, the GPL that covers the backend binary as a whole, CPython's, the
PyInstaller bootloader's, each bundled Python package's, fpcalc's, each Rust
crate's in the shell, and each npm package's in the interface.

Run by the release job after the backend build, after `npm ci`, after the
fpcalc sources are downloaded and after cargo-about has written the Rust
notices, because it reads all four.
"""

import argparse
import ast
import importlib.metadata
import json
import re
import subprocess
import sys
import tarfile
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path, PurePosixPath

from collect_python_sources import BUILD_DIR, bundled_distributions

RULE = "=" * 78
LICENCE_NAME = re.compile(r"(^|/)(LICEN[CS]E|COPYING|NOTICE)[^/]*$", re.IGNORECASE)
# The name pattern alone would also take a module called license.py, or a
# license.js, and pour its source into the notices. None of the bundled
# packages has one today; this is what keeps the day one arrives from going
# unnoticed.
CODE_SUFFIXES = {".py", ".pyc", ".pyi", ".pyd", ".so", ".js", ".mjs", ".cjs", ".ts"}
CHROMAPRINT_TARBALL = "chromaprint-1.6.1.tar.gz"
FFMPEG_TARBALL = "ffmpeg-8.0.tar.gz"
# The table of what the build finally collected. Analysis-00.toc would also
# list the libraries that the spec filters out after the analysis.
COLLECTED_TABLE = "COLLECT-00.toc"
DOC_DIR = Path("/usr/share/doc")

Section = tuple[str, str]
PackageFinder = Callable[[str], tuple[str, str] | None]

PREAMBLE = """\
Music Zamlr: licences of the installed program and its parts

The installer puts three programs on the computer, and each is distributed
under its own terms.

* The desktop window and the interface inside it are Music Zamlr's own code,
  under the MIT licence below. They also contain the Rust crates and the npm
  packages listed further down, each under the licence shown with it.

* The backend program (backend/music-zamlr-backend.exe and the files beside
  it) is distributed as a whole under the GNU General Public License,
  version 3 or any later version, whose text follows. It contains mutagen,
  which is licensed under the GPL version 2 or later, together with the
  Python runtime and the other Python packages listed below. Its complete
  source is attached to the same GitHub release as the installer: the
  repository's source archive and the archive of Python package sources.

* fpcalc (backend/fpcalc.exe) is distributed under the GNU Lesser General
  Public License, version 2.1, because it contains FFmpeg. Its source, with
  the scripts that built it, is the fpcalc sources archive attached to the
  same release.
"""


def licence_paths(paths: Iterable[str]) -> list[str]:
    """Keep the paths that name a licence or notice file, and not code."""
    kept = []
    for path in paths:
        posix = path.replace("\\", "/")
        if LICENCE_NAME.search(posix) and PurePosixPath(posix).suffix.lower() not in (
            CODE_SUFFIXES
        ):
            kept.append(path)
    return kept


def _distribution_texts(name: str) -> list[str]:
    # files() is None for a package installed without a RECORD, and that is
    # a package whose licence cannot be found, not an empty list of them.
    files = importlib.metadata.files(name) or []
    by_path = {str(file): file for file in files}
    texts = [
        by_path[path].read_text(encoding="utf-8") for path in licence_paths(by_path)
    ]
    if not texts:
        raise LookupError(f"No licence file found for the Python package {name}")
    return texts


def python_sections(build_dir: Path) -> list[Section]:
    # The same list collect_python_sources.py archives. Imported rather than
    # rebuilt, so the notices and the source archive cannot disagree about
    # what the binary contains.
    distributions = bundled_distributions(build_dir)
    sections = []
    for name in sorted(distributions, key=str.lower):
        body = "\n\n".join(_distribution_texts(name))
        sections.append((f"{name} {distributions[name]}", body))
    return sections


def npm_sections(frontend_dir: Path) -> list[Section]:
    # The lockfile rather than `npm ls`: it is the file `npm ci` installs
    # from, and reading it needs no subprocess, which on Windows would have
    # to be npm.cmd and not npm.
    lock = json.loads((frontend_dir / "package-lock.json").read_text(encoding="utf-8"))
    sections = []
    for key, entry in sorted(lock["packages"].items()):
        if not key.startswith("node_modules/") or entry.get("dev"):
            continue
        package_dir = frontend_dir / key
        texts = []
        if package_dir.is_dir():
            texts = [
                child.read_text(encoding="utf-8")
                for child in sorted(package_dir.iterdir())
                if child.is_file() and licence_paths([child.name])
            ]
        if not texts:
            raise LookupError(f"No licence file found for the npm package {key}")
        name = key.rsplit("node_modules/", 1)[-1]
        sections.append((f"{name} {entry['version']}", "\n\n".join(texts)))
    return sections


def _binary_sources(table: object) -> Iterator[tuple[str, str]]:
    # The same (name, path, kind) leaves that collect_python_sources.py walks
    # for modules, here for the shared libraries.
    if isinstance(table, (list, tuple)):
        if len(table) == 3 and all(isinstance(item, str) for item in table):
            if table[2] == "BINARY":
                yield table[0], table[1]
        else:
            for item in table:
                yield from _binary_sources(item)


def dpkg_package(path: str) -> tuple[str, str] | None:
    """Return the Debian package that installed a file, and its version."""
    # Ubuntu registers some libraries under /lib and some under /usr/lib, so
    # the resolved path is asked as well as the path PyInstaller recorded.
    for candidate in dict.fromkeys([path, str(Path(path).resolve())]):
        found = subprocess.run(
            ["dpkg", "-S", candidate], capture_output=True, text=True
        )
        if found.returncode == 0:
            package = found.stdout.splitlines()[0].split(":")[0]
            version = subprocess.run(
                ["dpkg-query", "-W", "-f=${Version}", package],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            return package, version
    return None


def system_sections(
    build_dir: Path,
    find_package: PackageFinder = dpkg_package,
    doc_dir: Path = DOC_DIR,
) -> list[Section]:
    """One section per system package whose libraries the backend bundles.

    Linux only: there PyInstaller copies the libraries that Python's modules
    need from the build machine, and each came from a package with its own
    licence. CPython's own files are covered by CPython's licence, and a
    wheel's by its package's, so neither is looked up.
    """
    table = ast.literal_eval((build_dir / COLLECTED_TABLE).read_text(encoding="utf-8"))
    files_by_package: dict[tuple[str, str], list[str]] = {}
    for name, source in _binary_sources(table):
        path = Path(source)
        if "site-packages" in path.parts or path.is_relative_to(sys.base_prefix):
            continue
        package = find_package(source)
        if package is None:
            raise LookupError(
                f"No package installed {source}, so its licence is unknown"
            )
        files_by_package.setdefault(package, []).append(name)

    sections = []
    for (package, version), names in sorted(files_by_package.items()):
        copyright_file = doc_dir / package / "copyright"
        if not copyright_file.is_file():
            raise LookupError(f"The package {package} has no {copyright_file}")
        heading = f"{package} {version} ({', '.join(sorted(names))})"
        sections.append((heading, copyright_file.read_text(encoding="utf-8")))
    return sections


def tarball_text(tarball: Path, name: str) -> str:
    """Return one file from a source tarball, wherever it sits inside."""
    with tarfile.open(tarball) as archive:
        for member in archive.getmembers():
            if member.isfile() and member.name.endswith("/" + name):
                return archive.extractfile(member).read().decode("utf-8")
    raise LookupError(f"{tarball.name} has no {name}")


def render(sections: list[Section]) -> str:
    parts = []
    for heading, body in sections:
        parts.append(f"{RULE}\n{heading}\n{RULE}\n\n{body.strip()}\n\n\n")
    return "".join(parts)


def _pyinstaller_bootloader() -> str:
    files = importlib.metadata.files("pyinstaller") or []
    paths = licence_paths(str(file) for file in files)
    if not paths:
        raise LookupError("No licence file found for PyInstaller")
    by_path = {str(file): file for file in files}
    return "\n\n".join(by_path[path].read_text(encoding="utf-8") for path in paths)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fpcalc-sources", type=Path, required=True)
    parser.add_argument("--rust-notices", type=Path, required=True)
    parser.add_argument("--frontend", type=Path, required=True)
    args = parser.parse_args()

    backend_dir = Path(__file__).resolve().parent
    repository = backend_dir.parent
    chromaprint = args.fpcalc_sources / CHROMAPRINT_TARBALL
    ffmpeg = args.fpcalc_sources / FFMPEG_TARBALL

    sections: list[Section] = [
        ("Music Zamlr", (repository / "LICENSE").read_text(encoding="utf-8")),
        (
            "GNU General Public License, version 3 (the backend program as a whole)",
            (repository / "licenses" / "GPL-3.0.txt").read_text(encoding="utf-8"),
        ),
        (
            f"Python {sys.version.split()[0]} (the runtime inside the backend program)",
            (Path(sys.base_prefix) / "LICENSE.txt").read_text(encoding="utf-8"),
        ),
        ("PyInstaller bootloader", _pyinstaller_bootloader()),
        *python_sections(backend_dir / BUILD_DIR),
        # Linux only. dpkg is what says where a library came from, and
        # Windows has none to ask.
        *(
            system_sections(backend_dir / BUILD_DIR)
            if sys.platform.startswith("linux")
            else []
        ),
        ("Chromaprint 1.6.1 (fpcalc)", tarball_text(chromaprint, "LICENSE.md")),
        ("FFmpeg 8.0 (inside fpcalc)", tarball_text(ffmpeg, "LICENSE.md")),
        (
            "GNU Lesser General Public License, version 2.1 (fpcalc)",
            tarball_text(ffmpeg, "COPYING.LGPLv2.1"),
        ),
        ("Rust crates", args.rust_notices.read_text(encoding="utf-8")),
        *npm_sections(args.frontend),
    ]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        PREAMBLE + "\n\n" + render(sections), encoding="utf-8", newline="\n"
    )


if __name__ == "__main__":
    main()
