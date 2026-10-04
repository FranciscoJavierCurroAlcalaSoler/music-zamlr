import io
import json
import tarfile

import pytest

from write_notices import licence_paths, npm_sections, tarball_text


def test_licence_paths_skips_code():
    # license.py is the case the suffix check exists for: its name matches,
    # and its contents are source code, not a licence.
    paths = [
        "pkg.dist-info/licenses/LICENSE",
        "pkg/license.py",
        "pkg/config/NOTICE",
        "pkg.dist-info/COPYING.txt",
    ]

    assert licence_paths(paths) == [
        "pkg.dist-info/licenses/LICENSE",
        "pkg/config/NOTICE",
        "pkg.dist-info/COPYING.txt",
    ]


def _frontend(tmp_path, packages):
    """A frontend folder with a lockfile and one directory per package."""
    lock = {"lockfileVersion": 3, "packages": {"": {"name": "frontend"}}}
    for name, (dev, licence) in packages.items():
        key = f"node_modules/{name}"
        lock["packages"][key] = {"version": "1.0.0", **({"dev": True} if dev else {})}
        package_dir = tmp_path / key
        package_dir.mkdir(parents=True)
        (package_dir / "package.json").write_text("{}")
        if licence:
            (package_dir / "LICENSE").write_text(f"{name} licence")
    (tmp_path / "package-lock.json").write_text(json.dumps(lock))
    return tmp_path


def test_npm_sections_leave_out_dev_dependencies(tmp_path):
    frontend = _frontend(tmp_path, {"react": (False, True), "vitest": (True, True)})

    sections = npm_sections(frontend)

    assert [heading for heading, _ in sections] == ["react 1.0.0"]


def test_an_npm_package_without_a_licence_stops_the_release(tmp_path):
    frontend = _frontend(tmp_path, {"unlicensed": (False, False)})

    with pytest.raises(LookupError):
        npm_sections(frontend)


def test_tarball_text_finds_a_nested_member(tmp_path):
    tarball = tmp_path / "pkg-1.0.tar.gz"
    content = b"the licence"
    with tarfile.open(tarball, "w:gz") as archive:
        member = tarfile.TarInfo("pkg-1.0/LICENSE.md")
        member.size = len(content)
        archive.addfile(member, io.BytesIO(content))

    assert tarball_text(tarball, "LICENSE.md") == "the licence"
    with pytest.raises(LookupError):
        tarball_text(tarball, "COPYING")
