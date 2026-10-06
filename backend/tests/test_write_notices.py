import io
import json
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

import write_notices
from write_notices import (
    COLLECTED_TABLE,
    GLIBC_TARBALL,
    PLATFORMS,
    RUST_TARGETS,
    current_platform,
    fpcalc_runtime_section,
    licence_paths,
    npm_sections,
    preamble,
    python_licence,
    rust_extension_sections,
    system_sections,
    tarball_text,
)


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


def _build(tmp_path, binaries):
    """A build folder whose collected table holds these BINARY entries."""
    build_dir = tmp_path / "build"
    build_dir.mkdir()
    entries = [(name, source, "BINARY") for name, source in binaries]
    entries.append(("base_library.zip", "/somewhere/base_library.zip", "DATA"))
    (build_dir / COLLECTED_TABLE).write_text(repr(([entries],)), encoding="utf-8")
    return build_dir


def _docs(tmp_path, *packages):
    doc_dir = tmp_path / "doc"
    for package in packages:
        (doc_dir / package).mkdir(parents=True)
        (doc_dir / package / "copyright").write_text(f"{package} copyright")
    return doc_dir


def _owners(mapping):
    calls = []

    def find_package(path):
        calls.append(path)
        return mapping.get(path)

    return find_package, calls


def test_system_sections_give_one_section_per_package(tmp_path):
    # libssl and libcrypto come from one package, whose copyright file has
    # to appear once, naming both files.
    build_dir = _build(
        tmp_path,
        [
            ("libssl.so.3", "/lib/x86_64-linux-gnu/libssl.so.3"),
            ("libcrypto.so.3", "/lib/x86_64-linux-gnu/libcrypto.so.3"),
            ("libz.so.1", "/lib/x86_64-linux-gnu/libz.so.1"),
        ],
    )
    find_package, _ = _owners(
        {
            "/lib/x86_64-linux-gnu/libssl.so.3": ("libssl3", "3.0.2"),
            "/lib/x86_64-linux-gnu/libcrypto.so.3": ("libssl3", "3.0.2"),
            "/lib/x86_64-linux-gnu/libz.so.1": ("zlib1g", "1.2.11"),
        }
    )

    sections = system_sections(
        build_dir, find_package, _docs(tmp_path, "libssl3", "zlib1g")
    )

    assert sections == [
        ("libssl3 3.0.2 (libcrypto.so.3, libssl.so.3)", "libssl3 copyright"),
        ("zlib1g 1.2.11 (libz.so.1)", "zlib1g copyright"),
    ]


def test_system_sections_leave_python_and_wheels_to_their_own_licences(tmp_path):
    # Neither is a system package, so asking dpkg about them would find
    # nothing and stop the release over files whose licences are covered.
    python_library = str(Path(sys.base_prefix) / "lib" / "libpython3.14.so.1.0")
    wheel_library = "/env/lib/python3.14/site-packages/pkg.libs/libpkg.so"
    build_dir = _build(
        tmp_path,
        [("libpython3.14.so.1.0", python_library), ("libpkg.so", wheel_library)],
    )
    find_package, calls = _owners({})

    assert system_sections(build_dir, find_package, _docs(tmp_path)) == []
    assert calls == []


def test_a_library_no_package_installed_stops_the_release(tmp_path):
    build_dir = _build(tmp_path, [("libmystery.so", "/opt/vendor/libmystery.so")])
    find_package, _ = _owners({})

    with pytest.raises(LookupError, match="libmystery"):
        system_sections(build_dir, find_package, _docs(tmp_path))


def test_a_package_without_a_copyright_file_stops_the_release(tmp_path):
    build_dir = _build(tmp_path, [("libz.so.1", "/lib/x86_64-linux-gnu/libz.so.1")])
    find_package, _ = _owners({"/lib/x86_64-linux-gnu/libz.so.1": ("zlib1g", "1.2.11")})

    with pytest.raises(LookupError, match="zlib1g"):
        system_sections(build_dir, find_package, _docs(tmp_path))


def _unwrapped(text):
    # Phrases are checked without the line breaks, which fall wherever the
    # width puts them.
    return " ".join(text.split())


def test_the_windows_preamble_names_its_files_and_runtimes():
    text = preamble("windows")

    assert "backend/fpcalc.exe" in text
    assert "MinGW-w64 runtime" in _unwrapped(text)
    assert "MSVCP140.dll" in text
    assert "GNU C Library" not in _unwrapped(text)


def test_the_linux_preamble_names_its_files_and_runtimes():
    # A Linux user reading ".exe" paths could not find a single file named.
    # The paths are checked in the wrapped text on purpose: "Music Zamlr"
    # holds a space, where a line break would split a path in two.
    text = preamble("linux")

    assert "/usr/lib/Music Zamlr/backend/fpcalc" in text
    assert "/usr/lib/Music Zamlr/backend/music-zamlr-backend" in text
    assert "GNU C Library" in _unwrapped(text)
    assert "system libraries" in _unwrapped(text)
    assert ".exe" not in text
    assert "MinGW" not in text


@pytest.mark.parametrize("platform", PLATFORMS)
def test_the_preamble_fits_the_width_of_the_rest(platform):
    assert max(len(line) for line in preamble(platform).splitlines()) <= 78


def test_windows_takes_the_mingw_notice_from_the_repository(tmp_path):
    (tmp_path / "licenses").mkdir()
    (tmp_path / "licenses" / "MinGW-w64-runtime.txt").write_text("mingw notice")

    heading, body = fpcalc_runtime_section("windows", tmp_path, tmp_path / "unused")

    assert "MinGW-w64" in heading
    assert body == "mingw notice"


def test_linux_takes_glibcs_notices_from_its_source(tmp_path):
    content = b"glibc notices"
    with tarfile.open(tmp_path / GLIBC_TARBALL, "w:xz") as archive:
        member = tarfile.TarInfo("glibc-2.35/LICENSES")
        member.size = len(content)
        archive.addfile(member, io.BytesIO(content))

    heading, body = fpcalc_runtime_section("linux", tmp_path / "unused", tmp_path)

    assert "GNU C Library" in heading
    assert body == "glibc notices"


def test_python_licence_is_found_where_each_platform_keeps_it(tmp_path):
    windows_like = tmp_path / "windows"
    windows_like.mkdir()
    (windows_like / "LICENSE.txt").write_text("at the top")
    linux_like = tmp_path / "linux"
    (linux_like / "lib" / "python3.14").mkdir(parents=True)
    (linux_like / "lib" / "python3.14" / "LICENSE.txt").write_text("in the stdlib")

    assert python_licence(windows_like, windows_like / "Lib") == "at the top"
    assert python_licence(linux_like, linux_like / "lib" / "python3.14") == (
        "in the stdlib"
    )
    with pytest.raises(LookupError):
        python_licence(tmp_path, tmp_path / "Lib")


@pytest.mark.parametrize(
    ("system", "expected"), [("win32", "windows"), ("linux", "linux")]
)
def test_the_notices_describe_the_platform_the_job_runs_on(
    monkeypatch, system, expected
):
    monkeypatch.setattr(write_notices.sys, "platform", system)

    assert current_platform() == expected


def test_no_notices_for_a_platform_with_no_release(monkeypatch):
    monkeypatch.setattr(write_notices.sys, "platform", "darwin")

    with pytest.raises(ValueError):
        current_platform()


def _sdist(folder, name, members):
    """A source archive holding these member paths, each with dummy text."""
    archive = folder / name
    if name.endswith(".zip"):
        with zipfile.ZipFile(archive, "w") as written:
            for member in members:
                written.writestr(member, "content")
    else:
        with tarfile.open(archive, "w:gz") as written:
            for member in members:
                info = tarfile.TarInfo(member)
                info.size = len(b"content")
                written.addfile(info, io.BytesIO(b"content"))
    return archive


def _recording_notices():
    calls = []

    def crate_notices(manifest, target):
        # Read while the archive is unpacked: the temporary folder is gone
        # once the section is built.
        calls.append((manifest.name, manifest.is_file(), target))
        return f"crates of {manifest.parent.name}"

    return crate_notices, calls


def test_a_python_package_built_from_rust_gets_its_crates(tmp_path):
    _sdist(
        tmp_path,
        "rusty_core-1.2.3.tar.gz",
        ["rusty_core-1.2.3/Cargo.lock", "rusty_core-1.2.3/Cargo.toml"],
    )
    _sdist(tmp_path, "plain-4.5.tar.gz", ["plain-4.5/setup.py"])
    (tmp_path / "MANIFEST.txt").write_text("plain==4.5\nrusty_core==1.2.3\n")
    crate_notices, calls = _recording_notices()

    sections = rust_extension_sections(tmp_path, "linux", crate_notices)

    assert sections == [
        (
            "rusty_core 1.2.3 (Rust crates compiled into it)",
            "crates of rusty_core-1.2.3",
        )
    ]
    assert calls == [("Cargo.toml", True, RUST_TARGETS["linux"])]


@pytest.mark.parametrize("platform", PLATFORMS)
def test_the_crates_are_those_of_the_platform_being_built(tmp_path, platform):
    # A crate can be a dependency on one target only, as the shell's
    # WebView2 and WebKitGTK crates are.
    _sdist(
        tmp_path,
        "rusty_core-1.2.3.tar.gz",
        ["rusty_core-1.2.3/Cargo.lock", "rusty_core-1.2.3/Cargo.toml"],
    )
    crate_notices, calls = _recording_notices()

    rust_extension_sections(tmp_path, platform, crate_notices)

    assert [target for _, _, target in calls] == [RUST_TARGETS[platform]]
    # Against the table itself the first assertion would pass with the two
    # targets swapped. Each target triple names its system.
    assert platform in RUST_TARGETS[platform]


def test_a_zip_source_archive_is_looked_into_as_well(tmp_path):
    _sdist(
        tmp_path,
        "zipped_core-0.1.zip",
        ["zipped_core-0.1/Cargo.lock", "zipped_core-0.1/Cargo.toml"],
    )
    crate_notices, _ = _recording_notices()

    sections = rust_extension_sections(tmp_path, "windows", crate_notices)

    assert [heading for heading, _ in sections] == [
        "zipped_core 0.1 (Rust crates compiled into it)"
    ]


def test_a_lockfile_deeper_in_a_package_is_not_its_own(tmp_path):
    # A package can carry a Rust project it does not build, as test data or
    # vendored source. Only a lockfile at its top describes its extension.
    _sdist(
        tmp_path,
        "carrier-2.0.tar.gz",
        ["carrier-2.0/setup.py", "carrier-2.0/vendor/thing/Cargo.lock"],
    )
    crate_notices, calls = _recording_notices()

    assert rust_extension_sections(tmp_path, "linux", crate_notices) == []
    assert calls == []
