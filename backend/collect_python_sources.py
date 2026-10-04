"""Download the source of every Python package inside the backend binary.

The binary bundles mutagen, which is GPL-2.0-or-later, so the binary is a
GPL work and every release must offer its complete corresponding source.
For the Python half of it that means the source distribution of each
package PyInstaller put into the bundle, at the version it put in.

The list comes from PyInstaller's own build tables, not from
requirements.txt, which is wrong in both directions: it names build and test
tools the binary never contains, and it would say nothing about a package
that reached the bundle without being pinned there.

Usage, from backend/ after `pyinstaller music-zamlr-backend.spec`, with the
Python that ran PyInstaller:

    python collect_python_sources.py <output-directory>
"""

import ast
import hashlib
import importlib.metadata
import json
import sys
import urllib.request
from collections.abc import Callable, Iterator
from pathlib import Path

BUILD_DIR = "build/music-zamlr-backend"
PYPI_JSON = "https://pypi.org/pypi/{name}/{version}/json"
TABLES = ("PYZ-00.toc", "Analysis-00.toc")
# EXTENSION as well as PYMODULE: a package that ships only a compiled module,
# with no Python beside it, appears in the build tables as nothing else.
MODULE_KINDS = {"PYMODULE", "EXTENSION"}


def _module_names(table: object) -> Iterator[str]:
    # The tables are nested lists and tuples whose leaves are
    # (name, path, kind) triples; their shape around those leaves differs
    # from one table to the other, so the walk does not assume it.
    if isinstance(table, (list, tuple)):
        if (
            len(table) == 3
            and all(isinstance(item, str) for item in table)
            and table[2] in MODULE_KINDS
        ):
            yield table[0]
        else:
            for item in table:
                yield from _module_names(item)


def bundled_distributions(build_dir: Path) -> dict[str, str]:
    """Map each distribution in the bundle to the version installed here.

    The versions are read from this interpreter's environment, so this has
    to run under the Python that ran PyInstaller. Any other would describe a
    different binary from the one being released.
    """
    top_level = set()
    for table_name in TABLES:
        table = ast.literal_eval((build_dir / table_name).read_text(encoding="utf-8"))
        top_level |= {name.split(".")[0] for name in _module_names(table)}

    owners = importlib.metadata.packages_distributions()
    distributions = {}
    for name in top_level:
        # Every owner, not the first. One top-level name can belong to
        # several distributions, and taking one would drop the source of
        # the others without a sign. A name with no owner is the standard
        # library, whose source is CPython's and not this list's concern.
        for distribution in owners.get(name, []):
            distributions[distribution] = importlib.metadata.version(distribution)
    return distributions


def sdist_url(
    name: str, version: str, opener: Callable = urllib.request.urlopen
) -> tuple[str, str]:
    """Return the URL and sha256 of the source distribution PyPI holds.

    PyPI's JSON rather than `pip download --no-binary :all:`, which runs a
    package's build backend to read its metadata: for pydantic-core that is
    maturin and a Rust compiler, so the release job would fail or start
    compiling. Fetching the file and checking its hash builds nothing.
    """
    with opener(PYPI_JSON.format(name=name, version=version), timeout=30) as response:
        data = json.load(response)
    for entry in data["urls"]:
        if entry["packagetype"] == "sdist":
            return entry["url"], entry["digests"]["sha256"]
    # Raised, never skipped: a release missing one package's source is a
    # release that breaches the licence, and it must not go out.
    raise LookupError(f"PyPI has no source distribution for {name}=={version}")


def main() -> None:
    output_dir = Path(sys.argv[1])
    output_dir.mkdir(parents=True, exist_ok=True)
    build_dir = Path(__file__).resolve().parent / BUILD_DIR
    distributions = bundled_distributions(build_dir)

    for name, version in sorted(
        distributions.items(), key=lambda item: item[0].lower()
    ):
        url, expected = sdist_url(name, version)
        with urllib.request.urlopen(url, timeout=120) as response:
            content = response.read()
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError(
                f"The source of {name}=={version} does not match PyPI's hash"
            )
        (output_dir / url.rsplit("/", 1)[-1]).write_bytes(content)

    # One line per package, so a reader sees what the archive covers without
    # opening forty files.
    manifest = sorted(f"{name}=={version}" for name, version in distributions.items())
    (output_dir / "MANIFEST.txt").write_text(
        "\n".join(manifest) + "\n", encoding="utf-8", newline="\n"
    )


if __name__ == "__main__":
    main()
