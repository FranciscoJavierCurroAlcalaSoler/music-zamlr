"""Fail the build when the bundle holds compiled code nobody has reviewed.

A package's licence file covers the package, not what was compiled into
it. A compiled extension can carry other projects' code (pydantic_core
carries Rust crates), and the notices must name each of them. A new
compiled package, or a new version of one, can bring such code without
any change in this repository besides requirements.txt, so each one has to
be looked at by a person before it ships.

The check reads the bundle from PyInstaller's build tables, as
collect_python_sources.py does, so it covers what the binary contains and
nothing else.

Usage, from backend/ after `pyinstaller music-zamlr-backend.spec`, with the
Python that ran PyInstaller:

    python check_compiled_packages.py
"""

import email.parser
import importlib.metadata
import re
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

from collect_python_sources import BUILD_DIR, bundled_distributions

# Each compiled package in the bundle, at the version whose compiled code
# was reviewed. The version is part of the key because a new release of a
# package can compile in a library the reviewed one did not have.
#
# To add or move an entry: find what the extension is built from (its
# sdist's Cargo.toml, setup.py, vendored directories), make sure the notices
# cover it, then write the version here.
AUDITED_COMPILED = {
    "greenlet": "3.5.3",
    "markupsafe": "3.0.3",
    "pydantic-core": "2.46.4",
    "sqlalchemy": "2.0.51",
    "websockets": "16.0",
}


def canonical_name(name: str) -> str:
    """The name in PEP 503's normal form: pydantic_core is pydantic-core.

    Installed metadata does not spell a name one way: the same package can
    arrive as MarkupSafe or markupsafe, with an underscore or a hyphen.
    Without this, a respelling would read as a package nobody reviewed.
    """
    return re.sub(r"[-_.]+", "-", name).lower()


def installed_wheel_text(name: str) -> str | None:
    return importlib.metadata.distribution(name).read_text("WHEEL")


def is_compiled(wheel_text: str | None) -> bool:
    """Say whether a distribution's WHEEL file marks it as platform-specific.

    Root-Is-Purelib, not a search for .pyd or .so files among the installed
    ones: a platform wheel can ship its compiled code as an executable or a
    shared library under any name.

    No WHEEL file at all means the package was installed some other way, so
    nothing says it is pure. It counts as compiled and goes to a person.
    """
    if wheel_text is None:
        return True
    headers = email.parser.Parser().parsestr(wheel_text)
    return headers.get("Root-Is-Purelib", "").strip().lower() != "true"


def unaudited(
    bundled: Mapping[str, str],
    wheel_text: Callable[[str], str | None],
    audited: Mapping[str, str],
) -> list[str]:
    """One line per compiled package that the audited list does not cover.

    An audited entry whose package left the bundle is not reported. The
    Windows and Linux bundles differ, and one list serves both.
    """
    findings = []
    for name, version in sorted(bundled.items(), key=lambda item: item[0].lower()):
        if not is_compiled(wheel_text(name)):
            continue
        reviewed = audited.get(canonical_name(name))
        if reviewed is None:
            findings.append(f"{name} {version}: compiled, and not on the list")
        elif reviewed != version:
            findings.append(f"{name} {version}: compiled, reviewed at {reviewed}")
    return findings


def main(
    build_dir: Path = Path(__file__).resolve().parent / BUILD_DIR,
    wheel_text: Callable[[str], str | None] = installed_wheel_text,
) -> int:
    findings = unaudited(bundled_distributions(build_dir), wheel_text, AUDITED_COMPILED)
    if not findings:
        print("Every compiled package in the bundle is on the audited list.")
        return 0
    # ::error:: makes GitHub show each line on the run's summary page, so
    # the email's link leads straight to the package names.
    for finding in findings:
        print(f"::error::{finding}")
    print(
        "Review what each package compiles in, make sure the notices cover "
        "it, then update AUDITED_COMPILED in check_compiled_packages.py."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
