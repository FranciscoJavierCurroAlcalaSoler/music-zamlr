import io
import json

import pytest

from collect_python_sources import bundled_distributions, sdist_url


def _write_tables(build_dir, pyz_entries, analysis_entries):
    # The real tables are Python literals: PYZ-00.toc a (path, [entries])
    # pair, Analysis-00.toc a longer tuple. The shapes only have to hold
    # (name, path, kind) triples somewhere inside them.
    build_dir.mkdir()
    (build_dir / "PYZ-00.toc").write_text(
        repr(("PYZ-00.pyz", pyz_entries)), encoding="utf-8"
    )
    (build_dir / "Analysis-00.toc").write_text(
        repr(([], analysis_entries)), encoding="utf-8"
    )


def _normalised(names):
    return {name.lower().replace("_", "-") for name in names}


def test_bundled_distributions_reads_extension_modules(tmp_path):
    # pydantic_core's compiled module stands alone in the analysis table,
    # which is how a package with no Python beside its extension appears.
    build_dir = tmp_path / "build"
    _write_tables(
        build_dir,
        pyz_entries=[],
        analysis_entries=[
            ("pydantic_core._pydantic_core", "C:\\x\\_pydantic_core.pyd", "EXTENSION")
        ],
    )

    assert "pydantic-core" in _normalised(bundled_distributions(build_dir))


def test_bundled_distributions_skips_the_standard_library(tmp_path):
    build_dir = tmp_path / "build"
    _write_tables(
        build_dir,
        pyz_entries=[
            ("json", "C:\\Python\\Lib\\json\\__init__.py", "PYMODULE"),
            ("sqlmodel", "C:\\site-packages\\sqlmodel\\__init__.py", "PYMODULE"),
        ],
        analysis_entries=[],
    )

    assert _normalised(bundled_distributions(build_dir)) == {"sqlmodel"}


def test_a_package_without_an_sdist_stops_the_release():
    # A stubbed PyPI, so the suite never reaches the network. The only file
    # on offer is a wheel, which is a binary and not source.
    def wheels_only(url, timeout):
        body = {
            "urls": [
                {
                    "packagetype": "bdist_wheel",
                    "url": "https://files.example/x.whl",
                    "digests": {"sha256": "0" * 64},
                }
            ]
        }
        return io.BytesIO(json.dumps(body).encode())

    with pytest.raises(LookupError):
        sdist_url("somepackage", "1.0", opener=wheels_only)
