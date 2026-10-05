"""Download the complete source of the fpcalc that a release ships.

fpcalc is LGPL-2.1 as a whole, because it links FFmpeg statically, and the
LGPL counts the scripts that control a library's compilation as part of its
source. Traced from the source rather than assumed: Chromaprint 1.6.1's
package/build.sh pins FFmpeg 8.0 from acoustid/ffmpeg-build's v8.0-1
release, and that repository's common.sh at the same tag fetches
ffmpeg-8.0.tar.gz from ffmpeg.org. The Linux binary is also linked with
-static, so it contains the C library of the machine that built it, and
that library's source travels with it too.

Usage, from backend/, with FPCALC_VERSION set as the workflows set it:

    python collect_fpcalc_sources.py <folder> --platform linux
"""

import argparse
import hashlib
import os
import urllib.request
from pathlib import Path
from typing import NamedTuple

# Every pin below belongs to this fpcalc and to nothing else. Raising the
# version in the workflows without tracing the new sources would ship a
# binary next to source that is not its own, with every check green.
FPCALC_VERSION = "1.6.1"
PLATFORMS = ("windows", "linux")
CHUNK_BYTES = 1 << 20


class Source(NamedTuple):
    url: str
    file: str
    sha256: str


# Pinned by hash. GitHub generates tag archives on demand and does not
# promise the same bytes every time. A mismatch stops the release, which is
# the right direction for a file the release must carry.
COMMON_SOURCES = (
    Source(
        "https://github.com/acoustid/chromaprint/releases/download/v1.6.1/chromaprint-1.6.1.tar.gz",
        "chromaprint-1.6.1.tar.gz",
        "3368805af0ee47b9df74df10b5001a44569e01df2844dab520031720dde9ad23",
    ),
    Source(
        "https://ffmpeg.org/releases/ffmpeg-8.0.tar.gz",
        "ffmpeg-8.0.tar.gz",
        "cce1136d38c389e6baaa452d6babc384cb2d3a9406ebe48c36a48f3ee115d8df",
    ),
    Source(
        "https://github.com/acoustid/ffmpeg-build/archive/refs/tags/v8.0-1.tar.gz",
        "ffmpeg-build-v8.0-1.tar.gz",
        "2533f000cc9d4ea72e5108c95bf2cc59770fa076ad8d4147e66ff5c16e42de14",
    ),
)

# Ubuntu 22.04's glibc as the build image of 2026-07-20 carried it, the
# image Chromaprint's release job ran on. The four files are one Debian
# source package; the hashes agree with the ones in Ubuntu's signed .dsc.
GLIBC_URL = (
    "https://launchpad.net/ubuntu/+archive/primary/+sourcefiles/glibc/2.35-0ubuntu3.13/"
)
LINUX_SOURCES = (
    Source(
        GLIBC_URL + "glibc_2.35-0ubuntu3.13.dsc",
        "glibc_2.35-0ubuntu3.13.dsc",
        "b8e7304bc899913294f1f1a2b2633f84f3ea93208f8da1a33e1340c4ad06e359",
    ),
    Source(
        GLIBC_URL + "glibc_2.35-0ubuntu3.13.debian.tar.xz",
        "glibc_2.35-0ubuntu3.13.debian.tar.xz",
        "28173285cf885df068374baf9b513ede397988ea3f93a1377f0268fe257a62f4",
    ),
    Source(
        GLIBC_URL + "glibc_2.35.orig.tar.xz",
        "glibc_2.35.orig.tar.xz",
        "5123732f6b67ccd319305efd399971d58592122bcc2a6518a1bd2510dd0cf52e",
    ),
    Source(
        GLIBC_URL + "glibc_2.35.orig.tar.xz.asc",
        "glibc_2.35.orig.tar.xz.asc",
        "853aaaf17d7366817e814057a467625ee7c0b26240e8b878db0f33c389c7bcb6",
    ),
)

README_OPENING = """\
The source of fpcalc 1.6.1, the fingerprinting program shipped with
Music Zamlr. fpcalc is distributed under the GNU Lesser General Public
License, version 2.1, because it is linked statically with FFmpeg.

chromaprint-1.6.1.tar.gz
    Chromaprint 1.6.1, which provides fpcalc. Its package/build.sh is
    the script that built the {platform} binary, and it names the FFmpeg
    build below.

ffmpeg-build-v8.0-1.tar.gz
    The scripts from acoustid/ffmpeg-build, release v8.0-1, that
    configured and compiled the FFmpeg libraries fpcalc links with.
    They configure FFmpeg without --enable-gpl and without
    --enable-nonfree, so the libraries are under the LGPL.

ffmpeg-8.0.tar.gz
    FFmpeg 8.0, as downloaded from ffmpeg.org by those scripts.
"""

README_GLIBC = """
glibc_2.35-0ubuntu3.13.dsc, glibc_2.35-0ubuntu3.13.debian.tar.xz,
glibc_2.35.orig.tar.xz, glibc_2.35.orig.tar.xz.asc
    The GNU C Library 2.35, as Ubuntu 22.04 packages it in version
    2.35-0ubuntu3.13. package/build.sh links the Linux fpcalc with
    -static, so the binary contains this library, which is under the
    GNU Lesser General Public License, version 2.1 or later. Unpack the
    four files with: dpkg-source -x glibc_2.35-0ubuntu3.13.dsc
"""

README_CLOSING = """
To rebuild fpcalc with a modified FFmpeg, build FFmpeg with the
scripts in ffmpeg-build-v8.0-1.tar.gz, then build Chromaprint against
it with package/build.sh.
"""

README_CLOSING_GLIBC = """
To rebuild it with a modified C library, build and install that
library first: package/build.sh links whichever one the system
provides.
"""


def sources_for(platform: str) -> tuple[Source, ...]:
    if platform == "linux":
        return COMMON_SOURCES + LINUX_SOURCES
    if platform == "windows":
        return COMMON_SOURCES
    raise ValueError(f"No fpcalc sources are pinned for the platform {platform}")


def readme(platform: str) -> str:
    text = README_OPENING.format(platform=platform.capitalize())
    if platform == "linux":
        return text + README_GLIBC + README_CLOSING + README_CLOSING_GLIBC
    return text + README_CLOSING


def check_fpcalc_version(version: str) -> None:
    if version != FPCALC_VERSION:
        raise ValueError(
            f"collect_fpcalc_sources.py pins the sources of fpcalc {FPCALC_VERSION},"
            f" not {version}. Trace and re-pin them."
        )


def download(source: Source, folder: Path, opener=urllib.request.urlopen) -> Path:
    """Download one source into the folder, and refuse it if the hash differs."""
    path = folder / source.file
    digest = hashlib.sha256()
    with opener(source.url) as response, path.open("wb") as output:
        while chunk := response.read(CHUNK_BYTES):
            digest.update(chunk)
            output.write(chunk)
    if digest.hexdigest() != source.sha256:
        # Deleted, so that a later step cannot archive the wrong bytes.
        path.unlink()
        raise ValueError(
            f"{source.file} has sha256 {digest.hexdigest()}, expected {source.sha256}"
        )
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", type=Path)
    parser.add_argument("--platform", choices=PLATFORMS, required=True)
    args = parser.parse_args()

    check_fpcalc_version(os.environ["FPCALC_VERSION"])
    args.folder.mkdir(parents=True, exist_ok=True)
    for source in sources_for(args.platform):
        download(source, args.folder)
    (args.folder / "README.txt").write_text(
        readme(args.platform), encoding="utf-8", newline="\n"
    )


if __name__ == "__main__":
    main()
