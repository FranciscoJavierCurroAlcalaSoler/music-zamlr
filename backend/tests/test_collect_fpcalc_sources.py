import hashlib
import io

import pytest

from collect_fpcalc_sources import (
    COMMON_SOURCES,
    FPCALC_VERSION,
    LINUX_SOURCES,
    PLATFORMS,
    Source,
    check_fpcalc_version,
    download,
    readme,
    sources_for,
)


def _opener(content):
    def opener(url):
        return io.BytesIO(content)

    return opener


def test_a_download_with_the_right_hash_is_kept(tmp_path):
    content = b"source bytes"
    source = Source(
        "https://example/a.tar.gz", "a.tar.gz", hashlib.sha256(content).hexdigest()
    )

    path = download(source, tmp_path, opener=_opener(content))

    assert path.read_bytes() == content


def test_a_download_with_the_wrong_hash_stops_and_leaves_nothing(tmp_path):
    # Left on disk, the wrong bytes would be archived by the next step even
    # though this one failed loudly.
    source = Source("https://example/a.tar.gz", "a.tar.gz", "0" * 64)

    with pytest.raises(ValueError, match="a.tar.gz"):
        download(source, tmp_path, opener=_opener(b"other bytes"))

    assert list(tmp_path.iterdir()) == []


def test_only_linux_carries_the_c_library():
    # The Windows binary links no glibc, and the Linux one contains it.
    assert sources_for("windows") == COMMON_SOURCES
    assert sources_for("linux") == COMMON_SOURCES + LINUX_SOURCES


@pytest.mark.parametrize("platform", PLATFORMS)
def test_the_readme_names_every_file_it_travels_with(platform):
    # A file the README does not explain is source nobody can place.
    text = readme(platform)

    for source in sources_for(platform):
        assert source.file in text
    assert f"built the {platform.capitalize()} binary" in text


def test_the_windows_readme_does_not_mention_the_c_library():
    assert "glibc" not in readme("windows")


def test_another_fpcalc_version_stops_the_collection():
    check_fpcalc_version(FPCALC_VERSION)

    with pytest.raises(ValueError, match="re-pin"):
        check_fpcalc_version("1.6.2")
